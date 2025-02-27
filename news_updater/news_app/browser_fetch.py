import logging
import time
import random
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

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
        from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException
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
        
        # Handle site-specific issues
        domain = url.split('//')[1].split('/')[0]
        
        # Handle SF Chronicle paywall/cookie consent
        if 'sfchronicle.com' in domain:
            try:
                # Try to close any cookie consent dialogs
                cookie_buttons = driver.find_elements(By.XPATH, "//button[contains(text(), 'Accept') or contains(text(), 'Agree') or contains(text(), 'Continue')]")
                for button in cookie_buttons:
                    try:
                        button.click()
                        logger.info("Clicked cookie consent button on SF Chronicle")
                        time.sleep(1)
                    except ElementClickInterceptedException:
                        pass
            except Exception as e:
                logger.warning(f"Error handling SF Chronicle specific elements: {str(e)}")
        
        # Handle Mercury News cookie consent and subscription dialogs
        if 'mercurynews.com' in domain:
            try:
                # Try to close any cookie consent dialogs
                cookie_buttons = driver.find_elements(By.XPATH, "//button[contains(text(), 'Accept') or contains(text(), 'Agree') or contains(text(), 'Continue')]")
                for button in cookie_buttons:
                    try:
                        button.click()
                        logger.info("Clicked cookie consent button on Mercury News")
                        time.sleep(1)
                    except ElementClickInterceptedException:
                        pass
                
                # Try to close subscription dialogs
                close_buttons = driver.find_elements(By.XPATH, "//button[contains(@class, 'close') or contains(@aria-label, 'Close')]")
                for button in close_buttons:
                    try:
                        button.click()
                        logger.info("Clicked close button on Mercury News")
                        time.sleep(1)
                    except ElementClickInterceptedException:
                        pass
            except Exception as e:
                logger.warning(f"Error handling Mercury News specific elements: {str(e)}")
        
        # Handle MV Voice specific issues
        if 'mv-voice.com' in domain:
            try:
                # Try to close any dialogs or popups
                close_buttons = driver.find_elements(By.XPATH, "//button[contains(@class, 'close') or contains(@aria-label, 'Close')]")
                for button in close_buttons:
                    try:
                        button.click()
                        logger.info("Clicked close button on MV Voice")
                        time.sleep(1)
                    except ElementClickInterceptedException:
                        pass
            except Exception as e:
                logger.warning(f"Error handling MV Voice specific elements: {str(e)}")
        
        # Scroll down to load lazy content
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
        time.sleep(2)  # Wait for content to load
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight*2/3);")
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
        
        # Site-specific selectors for problematic sites
        site_specific_selectors = {
            'mv-voice.com': ['.story', '.story-body', '.article-body', '.article-text'],
            'sfchronicle.com': ['.article-body', '.article', '.story-body', '.paywall-article'],
            'mercurynews.com': ['.article-body', '.entry-content', '.article', '.story-body']
        }
        
        # Check if we're on a site with specific selectors
        if any(site in domain for site in site_specific_selectors.keys()):
            for site, selectors in site_specific_selectors.items():
                if site in domain:
                    for selector in selectors:
                        try:
                            elements = driver.find_elements(By.CSS_SELECTOR, selector)
                            if elements:
                                # Get the HTML of the first matching element
                                main_content_html = elements[0].get_attribute('outerHTML')
                                main_content = BeautifulSoup(main_content_html, 'html.parser')
                                logger.info(f"Found main content using site-specific selector {selector} for {site}")
                                break
                        except Exception as e:
                            logger.warning(f"Error finding element with selector {selector}: {str(e)}")
                    if main_content:
                        break
        
        # If no site-specific selector worked, try generic selectors
        if not main_content:
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
        
        # Limit text length to avoid overwhelming Gemini
        return text[:15000] + "..." if len(text) > 15000 else text
        
    finally:
        if driver:
            driver.quit()
