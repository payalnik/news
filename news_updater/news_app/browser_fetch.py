import logging
import time
import random
import os
import shutil
import subprocess
import signal
import platform
import threading
from bs4 import BeautifulSoup
import requests
try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse

# Create specialized loggers
logger = logging.getLogger(__name__)
fetch_logger = logging.getLogger('news_app.fetch')

# Constants
TIMEOUT = 45  # Increased to be more realistic
MAX_CONTENT_LENGTH = 15000
# Updated generic User Agent
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"

# Deprecated: No longer kills global processes to be safe
def cleanup_browser_processes():
    pass

class BrowserSession:
    """
    Manages a persistent Playwright browser session.
    """
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None

    def __enter__(self):
        try:
            from playwright.sync_api import sync_playwright
            self.playwright = sync_playwright().start()
            
            # Anti-bot arguments
            args = [
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-blink-features=AutomationControlled',
                '--disable-extensions',
                '--window-size=1920,1080',
            ]
            
            self.browser = self.playwright.chromium.launch(
                headless=True,
                args=args
            )
            
            # Create a context with anti-bot configurations
            self.context = self.browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=USER_AGENT,
                locale='en-US',
                timezone_id='America/Los_Angeles'
            )
            
            # Add init scripts to mask automation
            self.context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            
            return self
        except Exception as e:
            logger.error(f"Failed to initialize BrowserSession: {e}")
            self.__exit__(None, None, None)
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.context:
            try:
                self.context.close()
            except Exception:
                pass
        if self.browser:
            try:
                self.browser.close()
            except Exception:
                pass
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception:
                pass
        self.context = None
        self.browser = None
        self.playwright = None

    def fetch_url(self, url):
        """Fetch content using the existing browser session."""
        if not self.context:
            raise RuntimeError("Browser session is not active")
            
        page = None
        try:
            page = self.context.new_page()
            
            # Realistic navigation
            try:
                page.goto(url, timeout=TIMEOUT * 1000, wait_until="domcontentloaded")
            except Exception as e:
                # If networkidle fails, try continuing anyway
                logger.warning(f"Navigation timeout/issue for {url}: {e}")
            
            # Allow some time for dynamic content
            time.sleep(2)
            
            # Scroll to trigger lazy loading
            try:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")
                time.sleep(1)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1)
            except Exception:
                pass
                
            content = page.content()
            return content
        except Exception as e:
            logger.error(f"Error fetching {url} with BrowserSession: {e}")
            return None
        finally:
            if page:
                try:
                    page.close()
                except Exception:
                    pass

def process_html_content(html_content, url):
    """Process HTML content using BeautifulSoup"""
    if not html_content:
        return ""
        
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove non-content elements
    for element in soup(["script", "style", "header", "footer", "nav", "aside", "noscript", "iframe", "svg", "button", "input", "form"]):
        element.extract()
    
    # Improved Domain handling
    try:
        domain = urlparse(url).netloc
        # Remove www.
        if domain.startswith('www.'):
            domain = domain[4:]
    except Exception:
        domain = url.split('//')[-1].split('/')[0]

    main_content = None
    
    # Expanded site-specific selectors
    site_specific_selectors = {
        'mv-voice.com': ['.story-body', '.article-body', '.story', '#article-body'],
        'paloaltoonline.com': ['.story-body', '.article-body', '.story'],
        'almanacnews.com': ['.story-body', '.article-body', '.story'],
        'sfchronicle.com': ['.article-body', '.article-text', '.story-body'],
        'mercurynews.com': ['.article-body', '.entry-content', '.body-content'],
        'nytimes.com': ['section[name="articleBody"]', '.StoryBodyCompanionColumn'],
        'washingtonpost.com': ['.article-body', '[data-qa="article-body"]'],
        'cnn.com': ['.article__content', '.zn-body__paragraph'],
        'bbc.com': ['article', '[data-component="text-block"]'],
        'reuters.com': ['.article-body__content__17Yit'],
    }
    
    # Check for site specific selectors
    for site, selectors in site_specific_selectors.items():
        if site in domain:
            for selector in selectors:
                content = soup.select(selector)
                if content:
                    # Join multiple elements if found (e.g. multiple paragraphs)
                    main_content_soup = BeautifulSoup("", 'html.parser')
                    for c in content:
                        main_content_soup.append(c)
                    main_content = main_content_soup
                    logger.info(f"Found main content using selector {selector} for {site}")
                    break
            if main_content:
                break
                
    if not main_content:
        # Generic content selectors ordered by likelihood
        content_selectors = [
            'article', 
            '[itemprop="articleBody"]', 
            '.article-body', 
            '.story-body',
            '.entry-content', 
            '.post-content',
            'main', 
            '#content', 
            '.content', 
            '#main', 
            '.main'
        ]
        for selector in content_selectors:
            content = soup.select(selector)
            if content:
                main_content = content[0]
                break
    
    if main_content:
        text = main_content.get_text(separator='\n')
    else:
        # Fallback to cleaning up body
        for element in soup.select('.ad, .ads, .advertisement, .sidebar, .comments, .related, .recommended, .social-share, .newsletter'):
            element.extract()
        text = soup.get_text(separator='\n')
        
    # Clean up text
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = '\n'.join(chunk for chunk in chunks if chunk)
    
    # Truncate
    final_text = text[:MAX_CONTENT_LENGTH] + "..." if len(text) > MAX_CONTENT_LENGTH else text
    return final_text

def fetch_with_playwright(url):
    """Fetch using Playwright (Single-use wrapper)"""
    try:
        logger.info("Attempting fetch with Playwright (One-off)")
        with BrowserSession() as session:
            return session.fetch_url(url)
    except Exception as e:
        logger.warning(f"Playwright fetch failed: {str(e)}")
        return None

def fetch_with_requests(url):
    """Fallback fetch using requests"""
    try:
        logger.info("Attempting fetch with Requests")
        headers = {
            'User-Agent': USER_AGENT,
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.google.com/'
        }
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        return response.text
    except Exception as e:
        logger.warning(f"Requests fetch failed: {str(e)}")
        return None

def _fetch_with_browser(url, browser_session=None):
    """
    Main entry point for fetching URL content.
    Supports optional persistent browser_session.
    """
    fetch_logger.info(f"Starting fetch for URL: {url}")
    
    html_content = None
    
    # 1. Try Playwright (Preferred)
    if browser_session:
        # Use provided session
        html_content = browser_session.fetch_url(url)
    else:
        # Create new session if none provided
        html_content = fetch_with_playwright(url)
    
    # 2. Try Requests (Fallback if Playwright failed)
    if not html_content:
        html_content = fetch_with_requests(url)
        
    if not html_content:
        # Don't raise generic exception, just return None so caller handles it
        logger.error(f"Failed to fetch content from {url} using all available methods")
        return None
        
    # 3. Process and Clean Content
    return process_html_content(html_content, url)
