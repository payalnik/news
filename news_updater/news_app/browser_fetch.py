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

# Create specialized loggers
logger = logging.getLogger(__name__)
fetch_logger = logging.getLogger('news_app.fetch')

# Constants
TIMEOUT = 30
MAX_CONTENT_LENGTH = 15000
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"

def cleanup_browser_processes():
    """Kill any existing Chrome/Chromium processes"""
    logger.info("Cleaning up any existing browser processes...")
    try:
        if os.name == 'nt':  # Windows
            subprocess.run(['taskkill', '/F', '/IM', 'chrome.exe'], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            subprocess.run(['taskkill', '/F', '/IM', 'chromium.exe'], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        else:  # Unix/Linux/Mac
            subprocess.run(['pkill', '-f', 'chrome'], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            subprocess.run(['pkill', '-f', 'chromium'], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            
            # Clean up /tmp
            try:
                for f in os.listdir('/tmp'):
                    if 'chrome' in f.lower() or 'chromium' in f.lower():
                        full_path = os.path.join('/tmp', f)
                        try:
                            if os.path.isdir(full_path):
                                shutil.rmtree(full_path, ignore_errors=True)
                            else:
                                os.remove(full_path)
                        except Exception:
                            pass
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Failed to kill existing browser processes: {str(e)}")

def process_html_content(html_content, url):
    """Process HTML content using BeautifulSoup"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove non-content elements
    for element in soup(["script", "style", "header", "footer", "nav", "aside", "noscript", "iframe"]):
        element.extract()
    
    # Domain specific handling
    domain = url.split('//')[1].split('/')[0]
    main_content = None
    
    site_specific_selectors = {
        'mv-voice.com': ['.story', '.story-body', '.article-body', '.article-text'],
        'sfchronicle.com': ['.article-body', '.article', '.story-body', '.paywall-article'],
        'mercurynews.com': ['.article-body', '.entry-content', '.article', '.story-body']
    }
    
    if any(site in domain for site in site_specific_selectors):
        for site, selectors in site_specific_selectors.items():
            if site in domain:
                for selector in selectors:
                    content = soup.select(selector)
                    if content:
                        main_content = content[0]
                        logger.info(f"Found main content using site-specific selector {selector} for {site}")
                        break
            if main_content:
                break
                
    if not main_content:
        content_selectors = [
            'main', 'article', '#content', '.content', '#main', '.main', '.article', '.post',
            '.story', '.entry', '[role="main"]', '.story-body', '.article-body', '.entry-content'
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
        for element in soup.select('.ad, .ads, .advertisement, .sidebar, .comments, .related, .recommended'):
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
    """Fetch using Playwright"""
    try:
        from playwright.sync_api import sync_playwright
        
        logger.info("Attempting fetch with Playwright")
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
            )
            
            try:
                page = browser.new_page(
                    viewport={"width": 1920, "height": 1080},
                    user_agent=USER_AGENT
                )
                
                page.goto(url, timeout=TIMEOUT * 1000)
                page.wait_for_load_state("networkidle", timeout=TIMEOUT * 1000)
                
                # Scroll to load lazy content
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1)
                
                content = page.content()
                logger.info("Successfully fetched with Playwright")
                return content
            finally:
                browser.close()
                
    except ImportError:
        logger.warning("Playwright not installed")
        return None
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
        }
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        return response.text
    except Exception as e:
        logger.warning(f"Requests fetch failed: {str(e)}")
        return None

def _fetch_with_browser(url):
    """
    Main entry point for fetching URL content using best available method.
    Tries Playwright -> Requests.
    """
    fetch_logger.info(f"Starting fetch for URL: {url}")
    
    # 1. Cleanup before starting
    cleanup_browser_processes()
    
    html_content = None
    
    # 2. Try Playwright (Preferred)
    html_content = fetch_with_playwright(url)
    
    # 3. Try Requests (Fallback)
    if not html_content:
        html_content = fetch_with_requests(url)
        
    if not html_content:
        raise Exception(f"Failed to fetch content from {url} using all available methods")
        
    # 5. Process and Clean Content
    return process_html_content(html_content, url)
