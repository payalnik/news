import logging
import time
import random
import os
import shutil
import subprocess
import requests
from bs4 import BeautifulSoup
from django.conf import settings

# Create specialized loggers
logger = logging.getLogger(__name__)
fetch_logger = logging.getLogger('news_app.fetch')

# Constants
TIMEOUT = 30
MAX_CONTENT_LENGTH = 60000  # Increased to match Jina limit
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/121.0.0.0 Safari/537.36'
]

def get_random_user_agent():
    return random.choice(USER_AGENTS)

def get_headers(url):
    ua = get_random_user_agent()
    is_chrome = 'Chrome' in ua
    
    headers = {
        'User-Agent': ua,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': 'https://www.google.com/',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'cross-site',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
    }
    
    if is_chrome:
        headers['sec-ch-ua'] = '"Google Chrome";v="121", "Not;A=Brand";v="8"'
        headers['sec-ch-ua-mobile'] = '?0'
        headers['sec-ch-ua-platform'] = '"Windows"' if 'Windows' in ua else '"macOS"'
        
    return headers

def cleanup_browser_processes():
    """Kill any existing Chrome/Chromium processes"""
    # Only run this if we are actually about to use a browser, to avoid side effects
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

def is_content_suitable_for_llm(text, url):
    """
    Check if the content is suitable for LLM processing.
    """
    if not text or len(text) < 200:
        logger.warning(f"Content from {url} is too short ({len(text) if text else 0} chars)")
        return False
    
    problematic_indicators = [
        "<html", "<body", "<script", "<style", "function(", "var ", "const ", "let ", "document.getElementById",
        "cookie policy", "accept cookies", "cookie settings", "privacy policy", "terms of service",
        "subscribe now", "subscription required", "create an account", "sign in to continue",
        "captcha", "robot", "automated access", "detection", "cloudflare",
        "404 not found", "403 forbidden", "access denied", "page not available",
        "loading", "please wait", "enable javascript", "browser not supported"
    ]
    
    indicator_count = 0
    text_lower = text.lower()
    for indicator in problematic_indicators:
        if indicator in text_lower:
            indicator_count += 1
            
    if indicator_count >= 3:
        logger.warning(f"Content from {url} has {indicator_count} problematic indicators")
        return False
    
    paragraphs = [p for p in text.split('\n') if p.strip()]
    meaningful_paragraphs = [p for p in paragraphs if len(p.split()) > 10]
    
    if len(meaningful_paragraphs) < 3:
        logger.warning(f"Content from {url} has only {len(meaningful_paragraphs)} meaningful paragraphs")
        return False
        
    return True

def process_html_content(html_content, url):
    """Process HTML content using BeautifulSoup"""
    if not html_content:
        return ""
        
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove non-content elements
    for element in soup(["script", "style", "header", "footer", "nav", "aside", "noscript", "iframe", "svg"]):
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

def fetch_with_jina(url):
    """Fetch URL content using Jina Reader API"""
    fetch_logger.info(f"Starting Jina-based fetch for URL: {url}")
    try:
        jina_url = f"https://r.jina.ai/{url}"
        headers = get_headers(url)
        headers['Referer'] = 'https://jina.ai/'
        
        response = requests.get(jina_url, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        
        text = response.text
        # Basic cleanup just in case
        soup = BeautifulSoup(text, 'html.parser')
        text = soup.get_text(separator='\n')
        
        if len(text) > MAX_CONTENT_LENGTH:
            text = text[:MAX_CONTENT_LENGTH] + "..."
            
        return text
    except Exception as e:
        fetch_logger.warning(f"Jina fetch failed for {url}: {str(e)}")
        return None

def fetch_with_playwright(url):
    """Fetch using Playwright"""
    try:
        from playwright.sync_api import sync_playwright
        
        logger.info("Attempting fetch with Playwright")
        cleanup_browser_processes()
        
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
            )
            
            try:
                page = browser.new_page(
                    viewport={"width": 1920, "height": 1080},
                    user_agent=get_random_user_agent()
                )
                
                page.goto(url, timeout=TIMEOUT * 1000)
                page.wait_for_load_state("domcontentloaded", timeout=TIMEOUT * 1000)
                
                # Scroll to load lazy content
                try:
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(2)
                except Exception:
                    pass
                
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

def fetch_with_selenium(url):
    """Fetch using Selenium"""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        logger.info("Attempting fetch with Selenium")
        cleanup_browser_processes()
        
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")  # Updated headless mode
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument(f"--user-agent={get_random_user_agent()}")
        
        driver = None
        try:
            # Try system/path driver first
            driver = webdriver.Chrome(options=chrome_options)
        except Exception:
            try:
                import chromedriver_autoinstaller
                chromedriver_autoinstaller.install()
                driver = webdriver.Chrome(options=chrome_options)
            except Exception:
                pass
                
        if not driver:
            logger.warning("Could not initialize Selenium driver")
            return None

        try:
            driver.set_page_load_timeout(TIMEOUT)
            driver.get(url)
            
            # Wait for body
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            except Exception:
                pass
            
            # Scroll
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
            return driver.page_source
        finally:
            try:
                driver.quit()
            except Exception:
                pass
            
    except ImportError:
        logger.warning("Selenium not installed")
        return None
    except Exception as e:
        logger.warning(f"Selenium fetch failed: {str(e)}")
        return None

def fetch_with_requests(url):
    """Fallback fetch using requests with realistic session"""
    try:
        logger.info("Attempting fetch with Requests")
        session = requests.Session()
        headers = get_headers(url)
        
        # Try to get homepage cookies first
        try:
            domain = url.split('//')[1].split('/')[0]
            session.get(f"https://{domain}", headers=headers, timeout=10)
        except Exception:
            pass
            
        response = session.get(url, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        return response.text
    except Exception as e:
        logger.warning(f"Requests fetch failed: {str(e)}")
        return None

def fetch_content(url, use_browser=None, use_jina=True):
    """
    Main entry point for fetching URL content.
    Strategy: Jina -> Requests -> Playwright -> Selenium
    """
    fetch_logger.info(f"Starting fetch for URL: {url}, use_browser={use_browser}, use_jina={use_jina}")
    
    # 1. Try Jina
    if use_jina:
        content = fetch_with_jina(url)
        if content and is_content_suitable_for_llm(content, url):
            fetch_logger.info("Successfully fetched and verified with Jina")
            return content
            
    # 2. Check for problematic sites that need browser
    domain = url.split('//')[1].split('/')[0]
    problematic_sites = ['mv-voice.com', 'paloaltoonline.com', 'almanacnews.com']
    force_browser = any(site in domain for site in problematic_sites)
    
    if force_browser:
        fetch_logger.info(f"Force browser enabled for {domain}")
        use_browser = True
    
    # 3. Try Requests (if not forced to use browser)
    if use_browser is not True:
        html = fetch_with_requests(url)
        if html:
            content = process_html_content(html, url)
            if is_content_suitable_for_llm(content, url):
                fetch_logger.info("Successfully fetched and verified with Requests")
                return content
            else:
                fetch_logger.info("Requests content not suitable, upgrading to browser")
        
    # 4. Try Browser (Playwright -> Selenium)
    if use_browser is not False:
        # Playwright
        html = fetch_with_playwright(url)
        if html:
            content = process_html_content(html, url)
            if is_content_suitable_for_llm(content, url):
                fetch_logger.info("Successfully fetched and verified with Playwright")
                return content
                
        # Selenium
        html = fetch_with_selenium(url)
        if html:
            content = process_html_content(html, url)
            if is_content_suitable_for_llm(content, url):
                fetch_logger.info("Successfully fetched and verified with Selenium")
                return content
                
    fetch_logger.error(f"Failed to fetch suitable content from {url} with any method")
    return None
