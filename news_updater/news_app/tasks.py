from celery import shared_task
from django.core.mail import send_mail, EmailMultiAlternatives
from django.utils.html import format_html
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
from .browser_fetch import _fetch_with_browser

# Create specialized loggers
logger = logging.getLogger(__name__)
fetch_logger = logging.getLogger('news_app.fetch')
gemini_logger = logging.getLogger('news_app.gemini')
preprocess_logger = logging.getLogger('news_app.preprocess')

# Try to import google.generativeai, but don't fail if it's not available
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logging.warning("google.generativeai module not available. Some features will be disabled.")

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
        
        Here is the raw content from the webpage:
        
        {content[:15000]}  # Limit content length to avoid token limits
        
        Return ONLY the cleaned, relevant news content. Do not add any commentary, summaries, or additional text.
        """
        
        preprocess_logger.info(f"Sending preprocessing request to Gemini for {url}")
        
        # Use Gemini Flash model for preprocessing (faster and cheaper than Pro)
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content(prompt)
        
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
    
    # Check for common indicators of problematic content
    problematic_indicators = [
        # HTML/JavaScript fragments that weren't properly cleaned
        "<html", "<body", "<script", "<style", "function(", "var ", "const ", "let ", "document.getElementById",
        # Indicators of cookie/paywall notices
        "cookie policy", "accept cookies", "cookie settings", "privacy policy", "terms of service",
        "subscribe now", "subscription required", "create an account", "sign in to continue",
        # Indicators of anti-bot measures
        "captcha", "robot", "automated access", "detection", "cloudflare",
        # Indicators of error pages
        "404 not found", "403 forbidden", "access denied", "page not available",
        # Indicators of content not loading properly
        "loading", "please wait", "enable javascript", "browser not supported"
    ]
    
    # Count problematic indicators
    indicator_count = 0
    for indicator in problematic_indicators:
        if indicator in text.lower():
            indicator_count += 1
            logger.debug(f"Found problematic indicator '{indicator}' in content from {url}")
    
    # If too many problematic indicators, consider content unsuitable
    if indicator_count >= 3:
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
    
    # Check for domain-specific issues
    domain = url.split('//')[1].split('/')[0]
    
    # MV Voice and related sites often have issues with content extraction
    if any(site in domain for site in ['mv-voice.com', 'paloaltoonline.com', 'almanacnews.com']):
        # For these sites, check for specific content patterns
        if "article" not in text.lower() and "story" not in text.lower():
            logger.warning(f"Content from {domain} doesn't appear to contain article text")
            return False
    
    # If we've passed all checks, the content seems suitable
    return True

@shared_task
def send_news_update(user_profile_id):
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
        if gemini_available:
            try:
                genai.configure(api_key=settings.GOOGLE_API_KEY)
            except Exception as e:
                logger.error(f"Error configuring Gemini: {str(e)}")
                gemini_available = False  # Only modify the local copy
        
        # Prepare email content
        plain_text_content = f"Hello {user.username},\n\nHere's your news update for {timezone.now().strftime('%Y-%m-%d')}:\n\n"
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; font-size: 16px; line-height: 1.4; color: #333; max-width: 800px; margin: 0 auto; padding: 10px; }}
                h1 {{ color: #2c3e50; font-size: 26px; }}
                h2 {{ color: #3498db; margin-top: 30px; padding-bottom: 10px; border-bottom: 1px solid #eee; font-size: 24px; }}
                .source-links {{ margin-top: 15px; margin-bottom: 25px; }}
                .source-links a {{ color: #2980b9; text-decoration: none; margin-right: 15px; }}
                .source-links a:hover {{ text-decoration: underline; }}
                .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee; font-size: 14px; color: #7f8c8d; }}
                .news-list {{ list-style-type: none; padding-left: 0; }}
                .news-item {{ margin-bottom: 25px; padding-bottom: 20px; border-bottom: 1px solid #eee; }}
                .news-item strong {{ font-size: 18px; color: #2c3e50; display: block; margin-bottom: 10px; }}
                .news-item p {{ margin-top: 5px; margin-bottom: 10px; font-size: 16px; }}
                .item-sources {{ font-size: 14px; color: #7f8c8d; margin-top: 8px; }}
                .item-sources a {{ color: #3498db; text-decoration: none; margin-right: 10px; }}
                .item-sources a:hover {{ text-decoration: underline; }}
            </style>
        </head>
        <body>
            <h1>News Update for {timezone.now().strftime('%Y-%m-%d')}</h1>
            <p>Hello {user.username},</p>
            <p>Here's your personalized news update:</p>
        """
        
        for section in news_sections:
            # Fetch content from sources
            sources_content = []
            source_urls = section.get_sources_list()
            
            for url in source_urls:
                try:
                    # Fetch the raw content
                    raw_content = fetch_url_content(url)
                    
                    # Preprocess the content with LLM to remove irrelevant information
                    preprocessed_content = preprocess_content_with_llm(raw_content, url)
                    
                    # Add the preprocessed content to the sources
                    sources_content.append(f"Content from {url}:\n{preprocessed_content}")
                except Exception as e:
                    logger.error(f"Error fetching content from {url}: {str(e)}")
                    sources_content.append(f"Error fetching content from {url}")
            
            # Get the last 100 news items for this user and section to avoid repetition
            recent_news_items = NewsItem.objects.filter(
                user_profile=user_profile,
                news_section=section
            ).order_by('-created_at')[:100]
            
            # Format previous news items to include in the prompt
            previous_news_items_text = ""
            if recent_news_items.exists():
                previous_news_items_text = "PREVIOUSLY REPORTED NEWS ITEMS (DO NOT REPEAT UNLESS SIGNIFICANT NEW DEVELOPMENTS):\n\n"
                for idx, item in enumerate(recent_news_items, 1):
                    previous_news_items_text += f"{idx}. Headline: {item.headline}\n"
                    previous_news_items_text += f"   Details: {item.details[:200]}{'...' if len(item.details) > 200 else ''}\n\n"
            
            # Generate summary using Gemini
            joined_sources = "\n\n".join(sources_content)
            prompt = f"""
            I need to create a news summary for the section "{section.name}" based on the following sources:
            
            {joined_sources}
            
            User's instructions for summarizing this section:
            {section.prompt}
            
            {previous_news_items_text}
            
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
            
            try:
                if not gemini_available:
                    # If Gemini is not available, provide a simple fallback
                    logger.warning(f"Gemini is not available. Using fallback for section {section.name}")
                    summary_text = f"Unable to generate summary for {section.name} because the Gemini API is not available. Please check the source links below for the original content."
                    valid_json = False
                else:
                    # Use Gemini Flash 2.0 model
                    gemini_logger.info(f"Sending request to Gemini for section '{section.name}'")
                    gemini_logger.info(f"Full prompt to Gemini:\n{prompt}")
                    
                    model = genai.GenerativeModel('gemini-2.0-flash')
                    response = model.generate_content(prompt)
                    
                    summary_text = response.text
                    gemini_logger.info(f"Received response from Gemini for section '{section.name}'")
                    gemini_logger.info(f"Full Gemini response:\n{summary_text}")
                
                    # Check if Gemini needs more information
                    if "I need more information" in summary_text or "need additional content" in summary_text:
                        # Handle the request for more information
                        # For now, we'll just include this in the email
                        pass
                
                # Try to parse the JSON response
                # Extract JSON array from the response if it's not a clean JSON
                gemini_logger.info(f"Attempting to parse JSON from Gemini response for section '{section.name}'")
                json_match = re.search(r'\[\s*\{.*\}\s*\]', summary_text, re.DOTALL)
                
                if json_match:
                    try:
                        json_str = json_match.group(0)
                        gemini_logger.info(f"Found JSON array in Gemini response, length: {len(json_str)} chars")
                        news_items = json.loads(json_str)
                        valid_json = True
                        gemini_logger.info(f"Successfully parsed JSON, found {len(news_items)} news items")
                    except json.JSONDecodeError as e:
                        valid_json = False
                        error_msg = f"Failed to parse JSON from Gemini response: {e}"
                        logger.error(error_msg)
                        gemini_logger.error(error_msg)
                        gemini_logger.error(f"JSON parsing error. Problematic JSON: {json_match.group(0)[:500]}...")
                else:
                    valid_json = False
                    error_msg = "No JSON array found in Gemini response"
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
                    
                    # Replace the original news_items with the filtered list
                    news_items = filtered_news_items
                    
                    # Log how many items were filtered out
                    filtered_count = len(news_items) - len(filtered_news_items)
                    if filtered_count > 0:
                        logger.info(f"Filtered out {filtered_count} duplicate news items for section {section.name}")
                
                # Add section to plain text email
                plain_text_content += f"\n\n## {section.name}\n\n"
                
                # Add section to HTML email
                html_content += f"<h2>{section.name}</h2>"
                
                if valid_json:
                    # Format the news items for plain text email
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
                        
                        headline = item.get("headline", "")
                        details = item.get("details", "")
                        sources = item.get("sources", [])
                        confidence = item.get("confidence", "")
                        
                        # Clean up source titles
                        cleaned_sources = []
                        for source in sources:
                            url = source.get("url", "")
                            title = source.get("title", "Article")
                            
                            # Extract domain name for cleaner display
                            domain = url.split("//")[-1].split("/")[0]
                            
                            # Clean up title - limit length and remove garbage text
                            # For news sites that often have long titles with multiple headlines
                            if len(title) > 60:  # If title is too long
                                # Try to get a cleaner title
                                if "New York Times" in title:
                                    title = "The New York Times"
                                elif "nytimes" in domain:
                                    title = "The New York Times"
                                elif "foxnews" in domain:
                                    title = "Fox News"
                                elif "cnn" in domain:
                                    title = "CNN"
                                elif "bbc" in domain:
                                    title = "BBC"
                                elif "washingtonpost" in domain:
                                    title = "Washington Post"
                                elif "wsj" in domain:
                                    title = "Wall Street Journal"
                                else:
                                    # Just use the domain name if we can't identify the source
                                    title = domain
                            
                            cleaned_sources.append({"url": url, "title": title})
                        
                        plain_text_content += f"* {headline}\n"
                        plain_text_content += f"  {details}\n"
                        if confidence:
                            plain_text_content += f"  Confidence: {confidence}\n"
                        if cleaned_sources:
                            plain_text_content += "  Sources: "
                            source_links = []
                            for source in cleaned_sources:
                                source_links.append(f"{source.get('title', 'Article')}: {source.get('url', '')}")
                            plain_text_content += ", ".join(source_links) + "\n\n"
                    
                    # Format the news items for HTML email
                    html_content += "<ul class='news-list'>"
                    for item in news_items:
                        headline = item.get("headline", "")
                        details = item.get("details", "")
                        sources = item.get("sources", [])
                        confidence = item.get("confidence", "")
                        
                        # Clean up source titles
                        cleaned_sources = []
                        for source in sources:
                            url = source.get("url", "")
                            title = source.get("title", "Article")
                            
                            # Extract domain name for cleaner display
                            domain = url.split("//")[-1].split("/")[0]
                            
                            # Clean up title - limit length and remove garbage text
                            # For news sites that often have long titles with multiple headlines
                            if len(title) > 60:  # If title is too long
                                # Try to get a cleaner title
                                if "New York Times" in title:
                                    title = "The New York Times"
                                elif "nytimes" in domain:
                                    title = "The New York Times"
                                elif "foxnews" in domain:
                                    title = "Fox News"
                                elif "cnn" in domain:
                                    title = "CNN"
                                elif "bbc" in domain:
                                    title = "BBC"
                                elif "washingtonpost" in domain:
                                    title = "Washington Post"
                                elif "wsj" in domain:
                                    title = "Wall Street Journal"
                                else:
                                    # Just use the domain name if we can't identify the source
                                    title = domain
                            
                            cleaned_sources.append({"url": url, "title": title})
                        
                        html_content += "<li class='news-item'>"
                        html_content += f"<strong>{headline}</strong>"
                        html_content += f"<p>{details}</p>"
                        
                        if confidence:
                            confidence_color = {
                                "high": "#28a745",
                                "medium": "#ffc107",
                                "low": "#dc3545"
                            }.get(confidence.lower(), "#6c757d")
                            
                            html_content += f"<div style='margin-top: 5px; font-size: 12px;'><span style='background-color: {confidence_color}; color: white; padding: 2px 6px; border-radius: 3px;'>Confidence: {confidence}</span></div>"
                        
                        if cleaned_sources:
                            html_content += "<div class='item-sources'>Sources: "
                            source_links = []
                            for source in cleaned_sources:
                                url = source.get("url", "")
                                title = source.get("title", "Article")
                                source_links.append(f"<a href='{url}' target='_blank'>{title}</a>")
                            html_content += ", ".join(source_links)
                            html_content += "</div>"
                        
                        html_content += "</li>"
                    html_content += "</ul>"
                else:
                    # Fallback to the old formatting if JSON parsing fails
                    plain_text_content += summary_text + "\n\n"
                    
                    # Convert the summary to HTML if it's not already in HTML format
                    if "<p>" not in summary_text:
                        # Split by paragraphs and wrap in <p> tags
                        paragraphs = summary_text.split("\n\n")
                        html_summary = ""
                        for para in paragraphs:
                            if para.strip():
                                # Check if this is a list item
                                if para.startswith("- ") or para.startswith("* "):
                                    # Convert to HTML list
                                    list_items = para.split("\n")
                                    html_summary += "<ul>"
                                    for item in list_items:
                                        if item.strip().startswith("- ") or item.strip().startswith("* "):
                                            item_content = item.strip()[2:].strip()
                                            html_summary += f"<li>{item_content}</li>"
                                    html_summary += "</ul>"
                                else:
                                    html_summary += f"<p>{para}</p>"
                    else:
                        # Already has HTML formatting
                        html_summary = summary_text
                    
                    # Ensure proper list formatting if there are any markdown-style lists that weren't caught
                    # First, identify paragraphs that are actually lists
                    if "<p>- " in html_summary or "<p>* " in html_summary:
                        # Split the HTML into chunks to process each paragraph separately
                        chunks = []
                        current_pos = 0
                        in_list = False
                        
                        # Process the HTML content to properly format lists
                        while current_pos < len(html_summary):
                            # Find the next paragraph start
                            p_start = html_summary.find("<p>", current_pos)
                            if p_start == -1:
                                # No more paragraphs, add the rest and break
                                chunks.append(html_summary[current_pos:])
                                break
                            
                            # Add content before this paragraph
                            if p_start > current_pos:
                                chunks.append(html_summary[current_pos:p_start])
                            
                            # Find the end of this paragraph
                            p_end = html_summary.find("</p>", p_start)
                            if p_end == -1:
                                # Malformed HTML, just add the rest and break
                                chunks.append(html_summary[current_pos:])
                                break
                            
                            p_content = html_summary[p_start:p_end+4]  # Include the </p>
                            
                            # Check if this paragraph is a list item
                            if p_content.startswith("<p>- ") or p_content.startswith("<p>* "):
                                # This is a list item
                                if not in_list:
                                    # Start a new list
                                    in_list = True
                                    item_content = p_content[5:].replace("</p>", "</li>")  # 5 to skip "<p>- " or "<p>* "
                                    chunks.append("<ul><li>" + item_content)
                                else:
                                    # Continue the list
                                    item_content = p_content[5:].replace("</p>", "</li>")  # 5 to skip "<p>- " or "<p>* "
                                    chunks.append("<li>" + item_content)
                            else:
                                # Not a list item
                                if in_list:
                                    # End the list before adding this paragraph
                                    in_list = False
                                    chunks.append("</ul>" + p_content)
                                else:
                                    # Regular paragraph
                                    chunks.append(p_content)
                            
                            current_pos = p_end + 4  # Move past </p>
                        
                        # If we ended while still in a list, close it
                        if in_
