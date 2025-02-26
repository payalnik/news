from celery import shared_task
from django.core.mail import send_mail, EmailMultiAlternatives
from django.utils.html import format_html
from django.conf import settings
from django.utils import timezone
import anthropic
import requests
from bs4 import BeautifulSoup
import logging
import random
import time
import json
import re

logger = logging.getLogger(__name__)

@shared_task
def send_news_update(user_profile_id):
    from .models import UserProfile, NewsSection
    
    try:
        user_profile = UserProfile.objects.get(id=user_profile_id)
        user = user_profile.user
        news_sections = NewsSection.objects.filter(user_profile=user_profile)
        
        if not news_sections.exists():
            logger.warning(f"No news sections found for user {user.username}")
            return
        
        # Initialize Anthropic client
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        
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
                    content = fetch_url_content(url)
                    sources_content.append(f"Content from {url}:\n{content}")
                except Exception as e:
                    logger.error(f"Error fetching content from {url}: {str(e)}")
                    sources_content.append(f"Error fetching content from {url}")
            
            # Generate summary using Claude
            joined_sources = "\n\n".join(sources_content)
            prompt = f"""
            I need to create a news summary for the section "{section.name}" based on the following sources:
            
            {joined_sources}
            
            User's instructions for summarizing this section:
            {section.prompt}
            
            Please provide a concise, well-organized summary of the most important news from these sources.
            
            IMPORTANT: Return your response as a JSON array with each news item having the following structure:
            {{
              "headline": "Headline of the news item",
              "details": "Detailed paragraph about the news item",
              "sources": [
                {{
                  "url": "URL of the source article",
                  "title": "Title of the source article"
                }}
              ]
            }}
            
            For example:
            [
              {{
                "headline": "Major Tech Company Announces New Product",
                "details": "The company revealed their latest innovation yesterday, featuring improved performance and new capabilities that industry analysts say could disrupt the market.",
                "sources": [
                  {{
                    "url": "https://example.com/tech-news/article1",
                    "title": "Tech Giant's New Release Stuns Industry"
                  }},
                  {{
                    "url": "https://another-site.com/business/tech-announcement",
                    "title": "Market Implications of the New Product Launch"
                  }}
                ]
              }},
              {{
                "headline": "Another Important News Item",
                "details": "Details about this news item...",
                "sources": [
                  {{
                    "url": "https://example.com/news/article2",
                    "title": "Article Title"
                  }}
                ]
              }}
            ]
            
            Make sure to:
            1. Include 3-5 of the most important news items from the sources unless stated otherwise
            2. Provide detailed but concise information in the details field
            3. Link to the original sources when possible
            4. Format the JSON correctly so it can be parsed
            
            If you need more information from any specific source, please indicate that outside the JSON structure.
            """
            
            try:
                response = client.messages.create(
                    model="claude-3-7-sonnet-20250219",
                    max_tokens=8000,
                    temperature=0.3,
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
                
                summary_text = response.content[0].text
                
                # Check if Claude needs more information
                if "I need more information" in summary_text or "need additional content" in summary_text:
                    # Handle the request for more information
                    # For now, we'll just include this in the email
                    pass
                
                # Try to parse the JSON response
                # Extract JSON array from the response if it's not a clean JSON
                json_match = re.search(r'\[\s*\{.*\}\s*\]', summary_text, re.DOTALL)
                
                if json_match:
                    try:
                        news_items = json.loads(json_match.group(0))
                        valid_json = True
                    except json.JSONDecodeError:
                        valid_json = False
                        logger.error(f"Failed to parse JSON from Claude response: {summary_text}")
                else:
                    valid_json = False
                    logger.error(f"No JSON array found in Claude response: {summary_text}")
                
                # Add section to plain text email
                plain_text_content += f"\n\n## {section.name}\n\n"
                
                # Add section to HTML email
                html_content += f"<h2>{section.name}</h2>"
                
                if valid_json:
                    # Format the news items for plain text email
                    for item in news_items:
                        headline = item.get("headline", "")
                        details = item.get("details", "")
                        sources = item.get("sources", [])
                        
                        plain_text_content += f"* {headline}\n"
                        plain_text_content += f"  {details}\n"
                        if sources:
                            plain_text_content += "  Sources: "
                            source_links = []
                            for source in sources:
                                source_links.append(f"{source.get('title', 'Article')}: {source.get('url', '')}")
                            plain_text_content += ", ".join(source_links) + "\n\n"
                    
                    # Format the news items for HTML email
                    html_content += "<ul class='news-list'>"
                    for item in news_items:
                        headline = item.get("headline", "")
                        details = item.get("details", "")
                        sources = item.get("sources", [])
                        
                        html_content += "<li class='news-item'>"
                        html_content += f"<strong>{headline}</strong>"
                        html_content += f"<p>{details}</p>"
                        
                        if sources:
                            html_content += "<div class='item-sources'>Sources: "
                            source_links = []
                            for source in sources:
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
                        if in_list:
                            chunks.append("</ul>")
                        
                        # Join all chunks to form the new HTML
                        html_summary = "".join(chunks)
                    
                    html_content += html_summary
                
                # Add source links section if we're not using the JSON format
                if not valid_json:
                    plain_text_content += "Sources:\n"
                    for url in source_urls:
                        plain_text_content += f"- {url}\n"
                    
                    html_content += '<div class="source-links"><strong>Sources:</strong> '
                    for url in source_urls:
                        domain = url.split("//")[-1].split("/")[0]
                        html_content += f'<a href="{url}" target="_blank">{domain}</a> '
                    html_content += '</div>'
                
            except Exception as e:
                logger.error(f"Error generating summary with Claude: {str(e)}")
                error_message = f"Error generating summary: {str(e)}"
                plain_text_content += f"\n\n## {section.name}\n\n{error_message}\n\n"
                html_content += f"<h2>{section.name}</h2><p>{error_message}</p>"
        
        # Complete HTML content
        html_content += """
            <div class="footer">
                <p>This email was automatically generated and sent by your News Updater service.</p>
            </div>
        </body>
        </html>
        """
        
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

def fetch_url_content(url, use_browser=None):
    """
    Fetch and extract text content from a URL with advanced browser simulation
    
    Args:
        url: The URL to fetch
        use_browser: None (auto-detect), True (force browser), False (force requests)
    """
    # Modern, up-to-date user agents
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/121.0.0.0 Safari/537.36'
    ]
    
    # Determine if we should use a headless browser
    if use_browser is None:
        # Auto-detect based on domain
        js_heavy_domains = ['nytimes.com', 'wsj.com', 'bloomberg.com', 'ft.com', 
                           'washingtonpost.com', 'economist.com', 'newyorker.com']
        use_browser = any(domain in url for domain in js_heavy_domains)
    
    # Try with headless browser if needed
    if use_browser:
        try:
            return _fetch_with_browser(url)
        except Exception as e:
            logger.error(f"Browser-based fetching failed for {url}: {str(e)}")
            logger.info(f"Falling back to requests-based fetching for {url}")
            # Fall back to requests-based fetching
    
    # More realistic browser headers
    chosen_ua = random.choice(user_agents)
    is_chrome = 'Chrome' in chosen_ua
    is_firefox = 'Firefox' in chosen_ua
    is_safari = 'Safari' in chosen_ua and 'Chrome' not in chosen_ua
    
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
    
    max_retries = 3
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
            response = session.get(url, headers=headers, timeout=15, cookies=cookies)
            response.raise_for_status()
            
            # Check if we got a valid response
            if not response.text or len(response.text) < 100:
                raise ValueError("Response too short, likely blocked or invalid")
            
            # Check for common anti-bot patterns
            if "captcha" in response.text.lower() or "cloudflare" in response.text.lower():
                logger.warning(f"Possible anti-bot protection detected on {url}")
                if attempt == max_retries - 1 and not use_browser:
                    logger.info(f"Trying with headless browser as last resort for {url}")
                    return _fetch_with_browser(url)
                else:
                    raise ValueError("Anti-bot protection detected")
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remove script, style, and other non-content elements
            for element in soup(["script", "style", "header", "footer", "nav", "aside", "iframe", "noscript"]):
                element.extract()
            
            # Try to find the main content area if possible
            main_content = None
            content_selectors = [
                'main', 'article', '#content', '.content', '#main', '.main', '.article', '.post',
                '.story', '.entry', '[role="main"]', '.story-body', '.article-body', '.entry-content',
                '.post-content', '.article-content', '.story-content'
            ]
            
            for tag in content_selectors:
                content = soup.select(tag)
                if content:
                    main_content = content[0]
                    break
            
            # If we found a main content area, use that, otherwise use the whole page
            if main_content:
                text = main_content.get_text(separator='\n')
            else:
                # Try to exclude common non-content areas
                for element in soup.select('.ad, .ads, .advertisement, .sidebar, .comments, .related, .recommended'):
                    element.extract()
                text = soup.get_text(separator='\n')
            
            # Process the text
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)
            
            # Check if we got enough content
            if len(text) < 500:
                logger.warning(f"Content from {url} seems too short ({len(text)} chars), might be incomplete")
                if attempt == max_retries - 1 and not use_browser:
                    logger.info(f"Content too short, trying with headless browser for {url}")
                    return _fetch_with_browser(url)
            
            # Limit text length to avoid overwhelming Claude
            return text[:15000] + "..." if len(text) > 15000 else text
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error fetching {url}: {str(e)}")
            if e.response.status_code in [403, 429]:
                logger.warning(f"Access denied (status {e.response.status_code}), might be rate limited or blocked")
                # On last retry with 403/429, try browser method if not already using it
                if attempt == max_retries - 1 and not use_browser:
                    logger.info(f"Trying with headless browser after receiving {e.response.status_code} for {url}")
                    return _fetch_with_browser(url)
            if attempt < max_retries - 1:
                # Add jitter to backoff
                jitter = random.uniform(0.8, 1.2)
                time.sleep(retry_delay * (attempt + 1) * jitter)  # Exponential backoff with jitter
            else:
                raise
        except requests.exceptions.ConnectionError:
            logger.error(f"Connection error fetching {url}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1) * random.uniform(0.8, 1.2))
            else:
                raise
        except requests.exceptions.Timeout:
            logger.error(f"Timeout fetching {url}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1) * random.uniform(0.8, 1.2))
            else:
                raise
        except Exception as e:
            logger.error(f"Error fetching {url}: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1) * random.uniform(0.8, 1.2))
            else:
                # On last retry with any error, try browser method if not already using it
                if not use_browser:
                    logger.info(f"Trying with headless browser as last resort for {url}")
                    return _fetch_with_browser(url)
                raise

def _fetch_with_browser(url):
    """Fetch URL content using a headless browser for JavaScript-heavy sites"""
    try:
        import selenium
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        import chromedriver_autoinstaller
    except ImportError:
        logger.error("Selenium not installed. Install with: pip install selenium chromedriver-autoinstaller")
        raise ImportError("Required packages not installed: selenium, chromedriver-autoinstaller")
    
    logger.info(f"Fetching {url} with headless browser")
    
    # Auto-install chromedriver
    chromedriver_autoinstaller.install()
    
    # Set up Chrome options
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # Add realistic browser fingerprint
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
    chrome_options.add_argument("--accept-lang=en-US,en;q=0.9")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    
    # Disable images for faster loading
    chrome_prefs = {
        "profile.default_content_settings": {"images": 2},
        "profile.managed_default_content_settings": {"images": 2}
    }
    chrome_options.add_experimental_option("prefs", chrome_prefs)
    
    driver = None
    try:
        driver = webdriver.Chrome(options=chrome_options)
        
        # Set page load timeout
        driver.set_page_load_timeout(30)
        
        # Navigate to the URL
        driver.get(url)
        
        # Wait for page to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        # Scroll down to load lazy content
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
        time.sleep(2)  # Wait for content to load
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)  # Wait for content to load
        
        # Get the page source
        page_source = driver.page_source
        
        # Parse with BeautifulSoup
        soup = BeautifulSoup(page_source, 'html.parser')
        
        # Remove script, style, and other non-content elements
        for element in soup(["script", "style", "header", "footer", "nav", "aside"]):
            element.extract()
        
        # Try to find the main content area
        main_content = None
        content_selectors = [
            'main', 'article', '#content', '.content', '#main', '.main', '.article', '.post',
            '.story', '.entry', '[role="main"]', '.story-body', '.article-body', '.entry-content',
            '.post-content', '.article-content', '.story-content'
        ]
        
        for tag in content_selectors:
            content = soup.select(tag)
            if content:
                main_content = content[0]
                break
        
        # If we found a main content area, use that, otherwise use the whole page
        if main_content:
            text = main_content.get_text(separator='\n')
        else:
            # Try to exclude common non-content areas
            for element in soup.select('.ad, .ads, .advertisement, .sidebar, .comments, .related, .recommended'):
                element.extract()
            text = soup.get_text(separator='\n')
        
        # Process the text
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        # Limit text length to avoid overwhelming Claude
        return text[:15000] + "..." if len(text) > 15000 else text
        
    finally:
        if driver:
            driver.quit()

@shared_task
def check_scheduled_emails():
    """Check if any emails need to be sent based on time slots"""
    from .models import TimeSlot
    
    current_time = timezone.now().time()
    # Round to nearest 30 minutes
    current_hour = current_time.hour
    current_minute = 30 if current_time.minute >= 30 else 0
    
    # Find all time slots matching the current time
    time_slots = TimeSlot.objects.filter(
        time__hour=current_hour,
        time__minute=current_minute
    )
    
    # Send emails for each user with a matching time slot
    for slot in time_slots:
        send_news_update.delay(slot.user_profile.id)
