from celery import shared_task
from django.core.mail import send_mail, EmailMultiAlternatives
from django.utils.html import format_html
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone
import logging
import os
import requests
from bs4 import BeautifulSoup
import random
import time
import json
import re
from urllib.parse import urljoin
from .browser_fetch import _fetch_with_browser, BrowserSession, process_html_content

# Try to import feedparser for RSS support
try:
    import feedparser
    FEEDPARSER_AVAILABLE = True
except ImportError:
    FEEDPARSER_AVAILABLE = False
    logging.warning("feedparser module not available. RSS feed support will be disabled.")

# Create specialized loggers
logger = logging.getLogger(__name__)
fetch_logger = logging.getLogger('news_app.fetch')
gemini_logger = logging.getLogger('news_app.gemini')
preprocess_logger = logging.getLogger('news_app.preprocess')

# Try to import google.generativeai, but don't fail if it's not available
try:
    import google.generativeai as genai
    from google import genai as google_genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logging.warning("google.generativeai or google-genai module not available. Some features will be disabled.")

def preprocess_content_with_llm(content, url):
    """
    Use LLM to preprocess the scraped content, removing irrelevant information
    and keeping only news items and links.
    
    Args:
        content: The raw scraped content from the website
        url: The source URL (for logging)
        
    Returns:
        str: Preprocessed content with only relevant news information
    """
    preprocess_logger.info(f"Starting LLM preprocessing for content from {url}")
    
    if not GEMINI_AVAILABLE:
        preprocess_logger.warning(f"Gemini not available for preprocessing content from {url}")
        return content
    
    try:
        # Configure Gemini
        genai.configure(api_key=settings.GOOGLE_API_KEY)
        client = google_genai.Client(api_key=settings.GOOGLE_API_KEY)
        
        # Create preprocessing prompt
        prompt = f"""
        I need you to clean and extract only the relevant news content from this webpage.
        
        Source URL: {url}
        
        INSTRUCTIONS:
        1. Remove all advertisements, navigation menus, footers, sidebars, and other non-content elements
        2. Keep ONLY actual news content: headlines, article text, and relevant links to news stories
        3. Preserve the structure of news items (headlines followed by content)
        4. Remove any user comments, social media widgets, or promotional content
        5. Keep image captions if they provide important context
        6. Maintain links to source articles or related news
        7. Format the output as plain text with clear separation between different news items
        8. If there are multiple news stories, separate them with "---" on a new line
        9. Remove utm_* variables from links
        10. If there are no news items, just leave 'No news items found'
        11. Remove duplicate news items if present (if the news is the same but the link differs, keep the link pointing to a specific story rather than the index page)
        
        Here is the raw content from the webpage:
        
        {content[:30000]}  # Limit content length to avoid token limits
        
        Return ONLY the cleaned, relevant news content. Do not add any commentary, summaries, or additional text.
        """
        
        preprocess_logger.info(f"Sending preprocessing request to Gemini for {url}")
        
        # Use Gemini Flash model for preprocessing (faster and cheaper than Pro)
        generate_content_config = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(
                thinking_level="MINIMAL",
            ),
        )

        response = client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=prompt,
            config=generate_content_config,
        )
        
        preprocessed_content = response.text
        
        # Log the results
        original_length = len(content)
        preprocessed_length = len(preprocessed_content)
        reduction_percentage = ((original_length - preprocessed_length) / original_length) * 100 if original_length > 0 else 0
        
        preprocess_logger.info(f"Preprocessing complete for {url}")
        preprocess_logger.info(f"Original content length: {original_length} chars")
        preprocess_logger.info(f"Preprocessed content length: {preprocessed_length} chars")
        preprocess_logger.info(f"Content reduction: {reduction_percentage:.1f}%")
        preprocess_logger.info(f"Preprocessed content preview (first 500 chars): {preprocessed_content[:500]}...")
        
        return preprocessed_content
        
    except Exception as e:
        preprocess_logger.error(f"Error preprocessing content with LLM: {str(e)}")
        # Fall back to original content if preprocessing fails
        return content

def is_content_suitable_for_llm(text, url):
    """
    Check if the content is suitable for LLM processing.
    
    Args:
        text: The extracted text content
        url: The source URL (for logging)
        
    Returns:
        bool: True if content appears suitable, False if it needs re-fetching
    """
    # Skip empty or very short content
    if not text or len(text) < 200:
        logger.warning(f"Content from {url} is too short ({len(text) if text else 0} chars)")
        return False
    
    # Check for strong indicators of problematic content
    # Only includes indicators that genuinely signal scrape failure
    problematic_indicators = [
        # HTML/JavaScript fragments that weren't properly parsed
        "<html", "<body", "<script", "<style",
        # Indicators of access/paywall blocks
        "captcha", "access denied", "403 forbidden", "404 not found",
        "page not available", "enable javascript", "browser not supported",
        "subscribe to continue", "subscription required", "sign in to continue",
    ]

    # Count problematic indicators
    indicator_count = 0
    for indicator in problematic_indicators:
        if indicator in text.lower():
            indicator_count += 1
            logger.debug(f"Found problematic indicator '{indicator}' in content from {url}")

    # Require more hits before rejecting — tighter list means fewer false positives
    if indicator_count >= 5:
        logger.warning(f"Content from {url} has {indicator_count} problematic indicators")
        return False
    
    # Check for coherent paragraphs - news articles typically have several paragraphs
    paragraphs = [p for p in text.split('\n') if p.strip()]
    meaningful_paragraphs = [p for p in paragraphs if len(p.split()) > 10]  # Paragraphs with >10 words
    
    if len(meaningful_paragraphs) < 3:
        logger.warning(f"Content from {url} has only {len(meaningful_paragraphs)} meaningful paragraphs")
        return False
    
    # Check for excessive repetition, which often indicates scraping issues
    words = text.lower().split()
    if len(words) > 100:
        # Get the 20 most common words (excluding very common words)
        from collections import Counter
        common_words = ["the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "of", "for", "with", "by"]
        word_counts = Counter([w for w in words if w not in common_words and len(w) > 3])
        most_common = word_counts.most_common(20)
        
        # If any word appears with very high frequency, it might indicate repetitive content
        for word, count in most_common:
            frequency = count / len(words)
            if frequency > 0.1 and count > 100:  # Word appears in >5% of text and >10 times
                logger.warning(f"Content from {url} has suspicious repetition of '{word}' ({count} times, {frequency:.1%})")
                return False
    
    # If we've passed all checks, the content seems suitable
    return True

@shared_task
def send_news_update(user_profile_id):
    # Fix for "You cannot call this from an async context" error
    # This usually happens when sync_playwright or other libs spin up an event loop
    # that confuses Django's synchronous ORM safety checks.
    os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
    
    try:
        from .models import UserProfile, NewsSection, NewsItem
        
        try:
            user_profile = UserProfile.objects.get(id=user_profile_id)
            user = user_profile.user
            news_sections = NewsSection.objects.filter(user_profile=user_profile)
            
            if not news_sections.exists():
                logger.warning(f"No news sections found for user {user.username}")
                return
            
            # Initialize Google Gemini client if available
            gemini_available = GEMINI_AVAILABLE  # Create a local copy of the global variable
            client = None
            if gemini_available:
                try:
                    genai.configure(api_key=settings.GOOGLE_API_KEY)
                    client = google_genai.Client(api_key=settings.GOOGLE_API_KEY)
                except Exception as e:
                    logger.error(f"Error configuring Gemini: {str(e)}")
                    gemini_available = False  # Only modify the local copy
            
            # Prepare data collection
            sections_data = []
            
            # Use a persistent browser session for all fetches in this task
            with BrowserSession() as browser_session:
                for section in news_sections:
                    # Fetch content from sources
                    sources_content = []
                    source_urls = section.get_sources_list()
                    
                    # Limit to 7 sources and set warning flag if limit exceeded
                    sources_limit_warning = False
                    if len(source_urls) > 7:
                        source_urls = source_urls[:7]
                        sources_limit_warning = True
                    
                    for url in source_urls:
                        try:
                            # Fetch the raw content, passing the shared browser session
                            raw_content = fetch_url_content(url, browser_session=browser_session)
                            
                            # Add the content to the sources directly (skipping redundant LLM preprocessing)
                            sources_content.append(f"Content from {url}:\n{raw_content}")
                        except Exception as e:
                            logger.error(f"Error fetching content from {url}: {str(e)}")
                            sources_content.append(f"Error fetching content from {url}")
                    
                    # Get the last 100 news items for this user and section to avoid repetition
                    recent_news_items = NewsItem.objects.filter(
                        user_profile=user_profile,
                        news_section=section
                    ).order_by('-created_at')[:100]
                    
                    # Format previous news items to include in the prompt
                    # Only include headlines from the last 7 days to save tokens;
                    # the full 100-item list is still used for post-generation is_similar_to() filtering.
                    previous_news_items_text = ""
                    if recent_news_items.exists():
                        from datetime import timedelta
                        seven_days_ago = timezone.now() - timedelta(days=7)
                        recent_headlines = [
                            item.headline for item in recent_news_items
                            if item.created_at >= seven_days_ago
                        ]
                        if recent_headlines:
                            previous_news_items_text = "PREVIOUSLY REPORTED NEWS ITEMS (DO NOT REPEAT UNLESS SIGNIFICANT NEW DEVELOPMENTS):\n\n"
                            for headline in recent_headlines:
                                previous_news_items_text += f"- {headline}\n"
                    
                    # Generate summary using Gemini
                    joined_sources = "\n\n".join(sources_content)
                    prompt = f"""
                    I need to create a news summary for the section "{section.name}" based on the following sources:
                    
                    {joined_sources}
                    
                    User's instructions for summarizing this section. Please follow them carefully, they take priority over any other guidelines:
                    {section.prompt}

                    -----------------
                    
                    {previous_news_items_text}

                    -----------------
                    
                    Please provide a concise, well-organized summary of the most important news from these sources.
                    
                    CRITICAL ANTI-HALLUCINATION INSTRUCTIONS:
                    1. ONLY include information that is EXPLICITLY stated in the provided sources
                    2. DO NOT add any details, context, or background information that is not directly from the sources
                    3. If the sources are insufficient to create a meaningful summary, state this clearly instead of inventing content
                    4. Each fact MUST be directly attributable to at least one of the provided sources
                    5. If sources contradict each other, note the contradiction and present both perspectives
                    6. Use phrases like "according to [source]" to clearly attribute information
                    7. If you're unsure about any information, indicate this uncertainty rather than making assumptions
                    8. DO NOT repeat news items that were previously reported unless there are significant new developments
                    
                    IMPORTANT: Return your response as a JSON array with each news item having the following structure:
                    {{
                      "headline": "Headline of the news item",
                      "details": "Detailed paragraph about the news item",
                      "sources": [
                        {{
                          "url": "URL of the source article",
                          "title": "Title of the source article (keep this short and clean, max 50 characters)"
                        }}
                      ],
                      "confidence": "high/medium/low" // Add your confidence level that this information is accurate and directly from sources
                    }}
                    
                    For example:
                    [
                      {{
                        "headline": "Major Tech Company Announces New Product",
                        "details": "According to Tech Giant's press release, the company revealed their latest innovation yesterday, featuring improved performance and new capabilities. Industry analysts quoted in the Market Implications article say this could disrupt the market.",
                        "sources": [
                          {{
                            "url": "https://example.com/tech-news/article1",
                            "title": "Tech Giant News"
                          }},
                          {{
                            "url": "https://another-site.com/business/tech-announcement",
                            "title": "Business Insider"
                          }}
                        ],
                        "confidence": "high"
                      }},
                      {{
                        "headline": "Another Important News Item",
                        "details": "Details about this news item, with clear attribution to sources...",
                        "sources": [
                          {{
                            "url": "https://example.com/news/article2",
                            "title": "Article Title"
                          }}
                        ],
                        "confidence": "medium"
                      }}
                    ]
                    
                    Make sure to:
                    1. Include 3-5 of the most important news items from the sources unless stated otherwise
                    2. Provide detailed but concise information in the details field WITH CLEAR ATTRIBUTION
                    3. Link to the original sources for EVERY claim made
                    4. Format the JSON correctly so it can be parsed
                    5. Include a confidence rating for each news item
                    6. Keep source titles short and clean (use the publication name like "The New York Times", "Fox News", "CNN", etc.)
                    7. If you cannot extract enough information from the sources, return a JSON array with a single item explaining the issue
                    
                    VERIFICATION STEP: Before finalizing your response, review each news item and verify:
                    - Every fact is directly from the sources
                    - No information has been added, assumed, or inferred beyond what's explicitly stated
                    - All claims are properly attributed
                    - The confidence rating accurately reflects the quality and clarity of the source information
                    - The news item is not a duplicate of previously reported items unless there are significant new developments
                    
                    If you need more information from any specific source, please indicate that outside the JSON structure.
                    """
                    
                    section_result = {
                        'name': section.name,
                        'items': [],
                        'error': None,
                        'sources_limit_warning': sources_limit_warning
                    }
                    
                    try:
                        if not gemini_available:
                            # If Gemini is not available, provide a simple fallback
                            logger.warning(f"Gemini is not available. Using fallback for section {section.name}")
                            section_result['error'] = f"Unable to generate summary for {section.name} because the Gemini API is not available. Please check the source links below for the original content."
                            valid_json = False
                        else:
                            # Use Gemini Flash 3 model with native JSON output
                            gemini_logger.info(f"Sending request to Gemini for section '{section.name}'")
                            gemini_logger.info(f"Full prompt to Gemini:\n{prompt}")
                            
                            # Define schema for the news items list
                            news_items_schema = types.Schema(
                                type=types.Type.ARRAY,
                                items=types.Schema(
                                    type=types.Type.OBJECT,
                                    properties={
                                        "headline": types.Schema(type=types.Type.STRING),
                                        "details": types.Schema(type=types.Type.STRING),
                                        "sources": types.Schema(
                                            type=types.Type.ARRAY,
                                            items=types.Schema(
                                                type=types.Type.OBJECT,
                                                properties={
                                                    "url": types.Schema(type=types.Type.STRING),
                                                    "title": types.Schema(type=types.Type.STRING),
                                                },
                                                required=["url", "title"]
                                            )
                                        ),
                                        "confidence": types.Schema(type=types.Type.STRING),
                                    },
                                    required=["headline", "details", "sources", "confidence"]
                                )
                            )
                            
                            generate_content_config = types.GenerateContentConfig(
                                thinking_config=types.ThinkingConfig(
                                    thinking_level="MINIMAL",
                                ),
                                response_mime_type="application/json",
                                response_schema=news_items_schema,
                            )

                            response = client.models.generate_content(
                                model='gemini-3-flash-preview',
                                contents=prompt,
                                config=generate_content_config,
                            )
                            
                            summary_text = response.text
                            gemini_logger.info(f"Received response from Gemini for section '{section.name}'")
                            gemini_logger.info(f"Full Gemini response:\n{summary_text}")
                        
                            # Check if Gemini needs more information
                            if "I need more information" in summary_text or "need additional content" in summary_text:
                                # Handle the request for more information
                                # For now, we'll just include this in the email
                                pass
                        
                        # Try to parse the JSON response
                        gemini_logger.info(f"Parsing JSON from Gemini response for section '{section.name}'")
                        
                        try:
                            # With native JSON mode, response should be valid JSON
                            news_items = json.loads(summary_text)
                            valid_json = True
                            gemini_logger.info(f"Successfully parsed JSON, found {len(news_items)} news items")
                        except json.JSONDecodeError as e:
                            # Fallback to regex extraction if native JSON failed (unlikely but possible)
                            gemini_logger.warning(f"Direct JSON parse failed: {e}. Attempting regex extraction.")
                            json_match = re.search(r'\[\s*\{.*\}\s*\]', summary_text, re.DOTALL)
                            if json_match:
                                try:
                                    json_str = json_match.group(0)
                                    news_items = json.loads(json_str)
                                    valid_json = True
                                    gemini_logger.info(f"Successfully parsed JSON via regex, found {len(news_items)} news items")
                                except json.JSONDecodeError as e2:
                                    valid_json = False
                                    error_msg = f"Failed to parse JSON from Gemini response (regex): {e2}"
                                    logger.error(error_msg)
                                    gemini_logger.error(error_msg)
                            else:
                                valid_json = False
                                error_msg = f"Failed to parse JSON from Gemini response: {e}"
                                logger.error(error_msg)
                                gemini_logger.error(f"{error_msg} for section '{section.name}'")
                        
                        # Filter out duplicate news items
                        if valid_json:
                            # Filter out duplicates or items without significant changes
                            filtered_news_items = []
                            for item in news_items:
                                headline = item.get("headline", "")
                                details = item.get("details", "")
                                
                                # Check if this is a duplicate of a recent news item
                                is_duplicate = False
                                for recent_item in recent_news_items:
                                    if recent_item.is_similar_to(headline, details):
                                        logger.info(f"Filtered out duplicate news item: {headline}")
                                        is_duplicate = True
                                        break
                                
                                if not is_duplicate:
                                    filtered_news_items.append(item)
                            
                            # Log how many items were filtered out
                            filtered_count = len(news_items) - len(filtered_news_items)
                            if filtered_count > 0:
                                logger.info(f"Filtered out {filtered_count} duplicate news items for section {section.name}")

                            # Replace the original news_items with the filtered list
                            news_items = filtered_news_items
                        
                        if valid_json:
                            # Process and store news items
                            for item in news_items:
                                # Store the news item in the database
                                headline = item.get("headline", "")
                                details = item.get("details", "")
                                sources = item.get("sources", [])
                                confidence = item.get("confidence", "medium")
                                
                                # Create a new NewsItem
                                news_item = NewsItem(
                                    user_profile=user_profile,
                                    news_section=section,
                                    headline=headline,
                                    details=details,
                                    confidence=confidence
                                )
                                news_item.set_sources_list(sources)
                                news_item.save()
                                
                                # Clean up source titles for display
                                cleaned_sources = []
                                for source in sources:
                                    url = source.get("url", "")
                                    title = source.get("title", "Article")
                                    
                                    # Extract domain name for cleaner display
                                    domain = url.split("//")[-1].split("/")[0]
                                    
                                    # Clean up title
                                    if len(title) > 60:
                                        if "New York Times" in title or "nytimes" in domain: title = "The New York Times"
                                        elif "foxnews" in domain: title = "Fox News"
                                        elif "cnn" in domain: title = "CNN"
                                        elif "bbc" in domain: title = "BBC"
                                        elif "washingtonpost" in domain: title = "Washington Post"
                                        elif "wsj" in domain: title = "Wall Street Journal"
                                        else: title = domain
                                    
                                    cleaned_sources.append({"url": url, "title": title})
                                
                                section_result['items'].append({
                                    'headline': headline,
                                    'details': details,
                                    'sources': cleaned_sources,
                                    'confidence': confidence
                                })

                        else:
                            # Fallback if JSON parsing fails
                            section_result['error'] = summary_text

                    except Exception as e:
                        logger.error(f"Error generating summary with Gemini: {str(e)}")
                        section_result['error'] = f"Error generating summary: {str(e)}"
                    
                    sections_data.append(section_result)
            
            # Generate HTML content using the template
            context = {
                'date': timezone.now().strftime('%Y-%m-%d'),
                'sections': sections_data,
                'dashboard_url': 'https://news.alexilin.com/dashboard/'
            }
            html_content = render_to_string('news_app/news_update_email.html', context)
            
            # Generate plain text content from the structured data
            plain_text_content = f"Here's your news update for {timezone.now().strftime('%Y-%m-%d')}:\n\n"
            
            for section in sections_data:
                plain_text_content += f"\n\n## {section['name']}\n\n"
                
                if section['error']:
                    plain_text_content += f"{section['error']}\n\n"
                else:
                    for item in section['items']:
                        plain_text_content += f"* {item['headline']}\n"
                        plain_text_content += f"  {item['details']}\n"
                        if item['sources']:
                            source_links = [f"{s['title']}: {s['url']}" for s in item['sources']]
                            plain_text_content += "  Sources: " + ", ".join(source_links) + "\n\n"
            
            plain_text_content += "\n\nEdit your news sections: https://news.alexilin.com/dashboard/"
            
            # Send email
            subject = f"Your News Update - {timezone.now().strftime('%Y-%m-%d')}"
            from_email = settings.DEFAULT_FROM_EMAIL
            recipient_list = [user.email]
            
            # Send both plain text and HTML versions
            email = EmailMultiAlternatives(
                subject=subject,
                body=plain_text_content,
                from_email=from_email,
                to=recipient_list
            )
            email.attach_alternative(html_content, "text/html")
            email.send()
            
            logger.info(f"News update sent to {user.email}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending news update: {str(e)}")
            return False
            
    finally:
        # Always clean up the env var
        if "DJANGO_ALLOW_ASYNC_UNSAFE" in os.environ:
            del os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"]

# Common RSS/Atom feed URL patterns to try for auto-discovery
RSS_FEED_PATHS = ['/feed', '/rss', '/rss/all', '/feeds/all.atom.xml', '/feed.xml', '/rss.xml', '/atom.xml', '/index.xml']


def _try_parse_feed(feed_url):
    """Fetch a feed URL with timeout and parse it. Returns parsed feed or None."""
    try:
        feed_resp = requests.get(feed_url, timeout=5, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        if feed_resp.status_code != 200:
            return None
        feed = feedparser.parse(feed_resp.content)
        if feed.entries:
            return feed
    except requests.RequestException:
        pass
    return None


def _format_feed(feed, feed_url):
    """Format a parsed feed into text content. Returns text or None if too short."""
    lines = []
    if feed.feed.get('title'):
        lines.append(f"# {feed.feed.title}")
        lines.append("")

    for entry in feed.entries[:30]:
        title = entry.get('title', 'Untitled')
        link = entry.get('link', '')
        summary = entry.get('summary', entry.get('description', ''))

        if summary and '<' in summary:
            soup = BeautifulSoup(summary, 'html.parser')
            summary = soup.get_text(separator=' ').strip()

        lines.append(f"## {title}")
        if link:
            lines.append(f"Link: {link}")
        if summary:
            if len(summary) > 1000:
                summary = summary[:1000] + "..."
            lines.append(summary)
        lines.append("")

    text = '\n'.join(lines)
    if len(text) > 500:
        fetch_logger.info(f"RSS feed content from {feed_url}: {len(text)} chars")
        return text[:60000] + "..." if len(text) > 60000 else text
    return None


def fetch_rss_feed(url):
    """
    Try to fetch content via RSS/Atom feed for the given URL.

    Discovery strategy (fast path first):
    1. Fetch the page HTML and look for <link rel="alternate"> feed tags
       - If found, try ONLY those (authoritative, skip common paths)
    2. Fall back to trying common feed URL patterns (/feed, /rss, etc.)
       - Give up after 3 consecutive misses

    Returns:
        str: Formatted feed content, or None if no feed found
    """
    if not FEEDPARSER_AVAILABLE:
        return None

    start_time = time.time()
    fetch_logger.info(f"Attempting RSS feed discovery for {url}")

    # Extract base URL (scheme + domain)
    try:
        parts = url.split('//')
        scheme = parts[0]
        domain = parts[1].split('/')[0]
        base_url = f"{scheme}//{domain}"
    except (IndexError, AttributeError):
        return None

    # Strategy 1: Fetch page and look for <link rel="alternate"> tags (authoritative)
    link_tag_feeds = []
    try:
        resp = requests.get(url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            for link in soup.find_all('link', rel='alternate'):
                link_type = (link.get('type') or '').lower()
                if 'rss' in link_type or 'atom' in link_type or 'xml' in link_type:
                    href = link.get('href', '')
                    if href:
                        full_url = urljoin(url, href)
                        # Skip comment feeds — they contain user comments, not articles
                        if '/comments' in full_url:
                            fetch_logger.debug(f"Skipping comment feed: {full_url}")
                            continue
                        link_tag_feeds.append(full_url)
    except Exception as e:
        fetch_logger.debug(f"Could not fetch page for RSS discovery: {e}")

    # If we found <link> feeds, try ONLY those (they're authoritative)
    if link_tag_feeds:
        seen = set()
        for feed_url in link_tag_feeds:
            if feed_url in seen:
                continue
            seen.add(feed_url)
            fetch_logger.debug(f"Trying <link> tag feed: {feed_url}")
            feed = _try_parse_feed(feed_url)
            if feed:
                fetch_logger.info(f"Found valid RSS feed at {feed_url} with {len(feed.entries)} entries")
                result = _format_feed(feed, feed_url)
                if result:
                    return result
        # <link> feeds didn't work out, fall through to common paths
        fetch_logger.debug(f"<link> tag feeds found but none had usable content")

    # Strategy 2: Try common feed URL patterns (give up after 3 consecutive misses)
    consecutive_misses = 0
    for path in RSS_FEED_PATHS:
        feed_url = base_url + path
        # Skip if already tried via <link> tags
        if feed_url in (link_tag_feeds or []):
            continue
        # Skip comment feeds
        if '/comments' in feed_url:
            continue

        fetch_logger.debug(f"Trying common feed path: {feed_url}")
        feed = _try_parse_feed(feed_url)
        if feed:
            fetch_logger.info(f"Found valid RSS feed at {feed_url} with {len(feed.entries)} entries")
            result = _format_feed(feed, feed_url)
            if result:
                return result
            consecutive_misses = 0
        else:
            consecutive_misses += 1
            if consecutive_misses >= 3:
                fetch_logger.debug(f"3 consecutive misses on common paths, giving up")
                break

    elapsed = time.time() - start_time
    fetch_logger.info(f"No RSS feed found for {url} ({elapsed:.1f}s)")
    return None


# Domains known to return 451 "Unavailable For Legal Reasons" from Jina Reader.
# Skip Jina entirely for these to avoid wasted time (1-30s per attempt).
JINA_BLOCKLIST = {
    'mercurynews.com',
    'theverge.com',
    'wired.com',
    'techcrunch.com',
    'apnews.com',
}


def fetch_with_jina(url):
    """
    Fetch URL content using Jina Reader API (r.jina.ai)
    
    Args:
        url: The URL to fetch
    """
    fetch_logger.info(f"Starting Jina-based fetch for URL: {url}")
    start_time = time.time()
    
    try:
        # Construct the Jina Reader API URL
        jina_url = f"https://r.jina.ai/{url}"
        
        # Set up headers to appear as a regular browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://jina.ai/',
            'DNT': '1',
        }
        
        # Make the request to Jina Reader
        fetch_logger.info(f"Sending request to Jina Reader for {url}")
        response = requests.get(jina_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Jina Reader returns markdown/text, not HTML — no BeautifulSoup needed
        text = response.text
        # Clean up excessive whitespace while preserving paragraph structure
        lines = (line.strip() for line in text.splitlines())
        text = '\n'.join(line for line in lines if line)
        
        elapsed_time = time.time() - start_time
        fetch_logger.info(f"Jina fetch completed in {elapsed_time:.2f} seconds")
        fetch_logger.info(f"Jina fetch for {url} completed, content length: {len(text)} chars")
        
        # Limit text length to avoid overwhelming Gemini
        return text[:60000] + "..." if len(text) > 60000 else text
        
    except Exception as e:
        elapsed_time = time.time() - start_time
        fetch_logger.error(f"Jina fetch failed for {url}: {str(e)}")
        # We'll let the function continue to try other methods
        fetch_logger.info(f"Falling back to other fetching methods for {url}")
        return None

def fetch_url_content(url, use_browser=None, use_jina=True, browser_session=None):
    """
    Fetch and extract text content from a URL with adaptive fetching methods
    
    Args:
        url: The URL to fetch
        use_browser: None (auto-detect), True (force browser), False (force requests)
        use_jina: True (try Jina first), False (skip Jina)
        browser_session: Optional BrowserSession object to reuse persistent browser
    """
    fetch_logger.info(f"Starting fetch for URL: {url}, use_browser={use_browser}, use_jina={use_jina}, session={bool(browser_session)}")
    
    # Try RSS/Atom feed first — most reliable source when available
    try:
        rss_content = fetch_rss_feed(url)
        if rss_content and len(rss_content) > 500:
            fetch_logger.info(f"Successfully fetched RSS feed content for {url}, length: {len(rss_content)} chars")
            if is_content_suitable_for_llm(rss_content, url):
                fetch_logger.info(f"RSS content is suitable for LLM processing")
                return rss_content
            else:
                fetch_logger.info(f"RSS content not suitable for LLM processing, trying other methods")
        else:
            fetch_logger.info(f"No RSS feed found for {url}, trying other methods")
    except Exception as e:
        fetch_logger.error(f"Error fetching RSS feed: {str(e)}")

    # Check if the domain is on the Jina blocklist
    domain = url.split('//')[1].split('/')[0]
    jina_blocked = any(blocked in domain for blocked in JINA_BLOCKLIST)
    if jina_blocked:
        fetch_logger.info(f"Skipping Jina for {domain} (blocklisted — returns 451)")

    # Try Jina first if enabled and not blocklisted
    if use_jina and not jina_blocked:
        try:
            fetch_logger.info(f"Attempting to fetch {url} using Jina Reader")
            jina_content = fetch_with_jina(url)
            if jina_content and len(jina_content) > 500:
                fetch_logger.info(f"Successfully fetched content with Jina Reader, length: {len(jina_content)} chars")
                
                # Check if the content is suitable for LLM processing
                if is_content_suitable_for_llm(jina_content, url):
                    fetch_logger.info(f"Jina content is suitable for LLM processing")
                    return jina_content
                else:
                    fetch_logger.info(f"Jina content not suitable for LLM processing, trying other methods")
            else:
                fetch_logger.info(f"Jina content too short or empty, trying other methods")
        except Exception as e:
            fetch_logger.error(f"Error using Jina Reader: {str(e)}")
    
    # Special handling for known problematic sites
    problematic_sites = ['mv-voice.com', 'paloaltoonline.com', 'almanacnews.com', 'axios.com', 'wsj.com']
    
    if any(site in domain for site in problematic_sites):
        fetch_logger.info(f"Known problematic site detected: {domain}. Using browser fetch directly.")
        content = _fetch_with_browser(url, browser_session=browser_session)
        if content:
            fetch_logger.info(f"Browser fetch for {url} completed, content length: {len(content)} chars")
        return content

    # Modern, up-to-date user agents
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/121.0.0.0 Safari/537.36'
    ]
    
    # If browser use is explicitly requested, use it
    if use_browser is True:
        try:
            return _fetch_with_browser(url, browser_session=browser_session)
        except Exception as e:
            logger.error(f"Browser-based fetching failed for {url}: {str(e)}")
            logger.info(f"Falling back to requests-based fetching for {url}")
            # Fall back to requests-based fetching
    
    # If browser use is explicitly forbidden, don't use it
    if use_browser is False:
        # Skip browser and go straight to requests
        pass
    
    # Otherwise, try requests first and fall back to browser if needed
    
    # More realistic browser headers
    chosen_ua = random.choice(user_agents)
    is_chrome = 'Chrome' in chosen_ua
    
    headers = {
        'User-Agent': chosen_ua,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': 'https://www.google.com/search?q=' + '+'.join(url.split('//')[1].split('/')[0].split('.')),
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'cross-site',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
    }
    
    # Browser-specific headers
    if is_chrome:
        headers['sec-ch-ua'] = '"Google Chrome";v="121", "Not;A=Brand";v="8"'
        headers['sec-ch-ua-mobile'] = '?0'
        headers['sec-ch-ua-platform'] = '"Windows"' if 'Windows' in chosen_ua else '"macOS"'
    
    # Create a session to maintain cookies
    session = requests.Session()
    
    # Set a realistic cookie
    cookies = {
        'visited': 'true',
        'session_id': f"{random.randint(1000000, 9999999)}",
        'consent': 'true',
    }
    
    max_retries = 2  # Reduced from 3 to 2 to try browser sooner
    retry_delay = 2  # seconds
    
    for attempt in range(max_retries):
        try:
            # Add jitter to appear more human-like
            if attempt > 0:
                jitter = random.uniform(0.5, 1.5)
                time.sleep(retry_delay * (attempt + 1) * jitter)
            
            logger.info(f"Fetching content from {url} (attempt {attempt+1}/{max_retries})")
            
            # First visit the domain homepage to set cookies
            if attempt == 0:
                domain = url.split('//')[1].split('/')[0]
                domain_url = f"https://{domain}"
                if domain_url != url:
                    try:
                        logger.info(f"First visiting domain homepage: {domain_url}")
                        session.get(domain_url, headers=headers, timeout=10, cookies=cookies)
                        # Small delay to simulate human browsing
                        time.sleep(random.uniform(1, 3))
                    except Exception as e:
                        logger.warning(f"Failed to visit domain homepage {domain_url}: {str(e)}")
            
            # Now fetch the actual URL
            fetch_logger.info(f"Fetching URL with requests: {url}")
            fetch_logger.info(f"Using headers: {headers}")
            response = session.get(url, headers=headers, timeout=15, cookies=cookies)
            response.raise_for_status()
            
            fetch_logger.info(f"Response received from {url}, status: {response.status_code}, content length: {len(response.text)} chars")
            
            # Check if we got a valid response
            if not response.text or len(response.text) < 100:
                fetch_logger.warning(f"Response too short from {url}, likely blocked or invalid")
                # Try with headless browser immediately if content is too short
                fetch_logger.info(f"Response too short, trying with headless browser for {url}")
                content = _fetch_with_browser(url, browser_session=browser_session)
                if content:
                    fetch_logger.info(f"Browser fetch for {url} completed, content length: {len(content)} chars")
                return content
            
            # Check for common anti-bot patterns
            if "captcha" in response.text.lower() or "cloudflare" in response.text.lower():
                logger.warning(f"Possible anti-bot protection detected on {url}")
                # Try with headless browser immediately if anti-bot protection is detected
                logger.info(f"Anti-bot protection detected, trying with headless browser for {url}")
                return _fetch_with_browser(url, browser_session=browser_session)
            
            # Use improved processing from browser_fetch
            # Pass bytes (response.content) to let BeautifulSoup detect encoding
            return process_html_content(response.content, url)
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error fetching {url}: {str(e)}")
            if e.response.status_code in [403, 429]:
                logger.warning(f"Access denied (status {e.response.status_code}), might be rate limited or blocked")
                # Try with headless browser immediately if we get a 403 or 429
                logger.info(f"Access denied, trying with headless browser for {url}")
                return _fetch_with_browser(url, browser_session=browser_session)
            if attempt < max_retries - 1:
                # Add jitter to backoff
                jitter = random.uniform(0.8, 1.2)
                time.sleep(retry_delay * (attempt + 1) * jitter)  # Exponential backoff with jitter
            else:
                # On last retry, try browser method
                logger.info(f"Multiple HTTP errors, trying with headless browser for {url}")
                return _fetch_with_browser(url, browser_session=browser_session)
        except requests.exceptions.ConnectionError:
            logger.error(f"Connection error fetching {url}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1) * random.uniform(0.8, 1.2))
            else:
                # On last retry, try browser method
                logger.info(f"Connection errors, trying with headless browser for {url}")
                return _fetch_with_browser(url, browser_session=browser_session)
        except requests.exceptions.Timeout:
            logger.error(f"Timeout fetching {url}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1) * random.uniform(0.8, 1.2))
            else:
                # On last retry, try browser method
                logger.info(f"Timeout errors, trying with headless browser for {url}")
                return _fetch_with_browser(url, browser_session=browser_session)
        except Exception as e:
            logger.error(f"Error fetching {url}: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1) * random.uniform(0.8, 1.2))
            else:
                # On last retry, try browser method
                logger.info(f"Multiple errors, trying with headless browser for {url}")
                return _fetch_with_browser(url, browser_session=browser_session)

@shared_task
def cleanup_old_news_items():
    """Clean up old news items to prevent database bloat"""
    from .models import NewsItem
    from django.utils import timezone
    from datetime import timedelta
    
    # Keep news items from the last 30 days
    cutoff_date = timezone.now() - timedelta(days=30)
    
    # Get all news items older than the cutoff date, but ensure we keep at least 100 most recent items per section
    old_items = NewsItem.objects.filter(created_at__lt=cutoff_date)
    
    # Get a list of all user_profile and news_section combinations
    from django.db.models import Count
    section_counts = NewsItem.objects.values('user_profile', 'news_section').annotate(
        count=Count('id')
    )
    
    # For each combination, ensure we keep at least 100 items
    protected_ids = []
    
    for section_data in section_counts:
        user_profile_id = section_data['user_profile']
        news_section_id = section_data['news_section']
        
        # Get the IDs of the most recent 100 items for this section
        recent_ids = NewsItem.objects.filter(
            user_profile_id=user_profile_id,
            news_section_id=news_section_id
        ).order_by('-created_at')[:100].values_list('id', flat=True)
        
        protected_ids.extend(list(recent_ids))
    
    # Exclude the protected IDs from deletion
    items_to_delete = old_items.exclude(id__in=protected_ids)
    delete_count = items_to_delete.count()
    
    if delete_count > 0:
        deleted, _ = items_to_delete.delete()
        logger.info(f'Cleaned up {deleted} old news items')
    else:
        logger.info('No old news items to clean up')
    
    return delete_count

@shared_task
def check_scheduled_emails():
    """Check if any emails need to be sent based on time slots"""
    from .models import TimeSlot
    from datetime import timedelta
    
    # Get current UTC time
    current_time = timezone.now().astimezone(timezone.utc)
    current_time_only = current_time.time()
    
    # Calculate time 5 minutes ago
    five_mins_ago = current_time - timedelta(minutes=5)
    five_mins_ago_time = five_mins_ago.time()
    
    # Log the current time for debugging
    logger.info(f"Checking for scheduled emails at UTC time {current_time_only.strftime('%H:%M')}")
    logger.info(f"Looking for time slots between {five_mins_ago_time.strftime('%H:%M')} and {current_time_only.strftime('%H:%M')}")
    
    # Find time slots in the last 5 minutes
    # Handle the case where the time range crosses midnight
    if five_mins_ago_time > current_time_only:
        # Time range crosses midnight
        time_slots = TimeSlot.objects.filter(
            time__gte=five_mins_ago_time
        ) | TimeSlot.objects.filter(
            time__lte=current_time_only
        )
    else:
        # Normal time range within the same day
        time_slots = TimeSlot.objects.filter(
            time__gte=five_mins_ago_time,
            time__lte=current_time_only
        )
    
    # Log the number of matching time slots
    logger.info(f"Found {time_slots.count()} matching time slots")
    
    # Send emails for each user with a matching time slot
    for slot in time_slots:
        logger.info(f"Scheduling email for user {slot.user_profile.user.username} at {slot.time}")
        send_news_update.delay(slot.user_profile.id)
