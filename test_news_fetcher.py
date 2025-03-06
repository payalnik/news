#!/usr/bin/env python
import os
import sys
import logging
import argparse
import time
from bs4 import BeautifulSoup

# Set up Django environment
sys.path.append(os.path.join(os.path.dirname(__file__), 'news_updater'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'news_updater.settings')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('news_fetcher_test.log')
    ]
)

logger = logging.getLogger('test_news_fetcher')
fetch_logger = logging.getLogger('news_app.fetch')
fetch_logger.setLevel(logging.DEBUG)

def test_jina_fetch(url):
    """Test fetching content using the Jina Reader method"""
    logger.info(f"Testing Jina Reader-based fetch for URL: {url}")
    start_time = time.time()
    
    try:
        # Import the fetch_with_jina function
        from news_updater.news_app.tasks import fetch_with_jina
        
        logger.info(f"Calling fetch_with_jina for {url}")
        content = fetch_with_jina(url)
        
        if not content:
            raise Exception("Jina Reader returned empty content")
        
        elapsed_time = time.time() - start_time
        logger.info(f"Jina fetch completed in {elapsed_time:.2f} seconds")
        
        return {
            "success": True,
            "method": "jina",
            "content_length": len(content),
            "elapsed_time": elapsed_time,
            "content": content
        }
    
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(f"Jina fetch failed: {str(e)}")
        return {
            "success": False,
            "method": "jina",
            "error": str(e),
            "elapsed_time": elapsed_time,
            "content": None
        }

def test_requests_fetch(url):
    """Test fetching content using the requests method"""
    logger.info(f"Testing requests-based fetch for URL: {url}")
    start_time = time.time()
    
    try:
        import requests
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.google.com/',
            'DNT': '1',
        }
        
        logger.info(f"Sending request to {url}")
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        logger.info(f"Response received, status: {response.status_code}, content length: {len(response.text)} chars")
        
        # Parse with BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Remove script, style, and other non-content elements
        for element in soup(["script", "style", "header", "footer", "nav", "aside"]):
            element.extract()
        
        # Process the text
        text = soup.get_text(separator='\n')
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        elapsed_time = time.time() - start_time
        logger.info(f"Requests fetch completed in {elapsed_time:.2f} seconds")
        
        return {
            "success": True,
            "method": "requests",
            "content_length": len(text),
            "elapsed_time": elapsed_time,
            "content": text[:15000] + "..." if len(text) > 15000 else text
        }
    
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(f"Requests fetch failed: {str(e)}")
        return {
            "success": False,
            "method": "requests",
            "error": str(e),
            "elapsed_time": elapsed_time,
            "content": None
        }

def test_browser_fetch(url):
    """Test fetching content using the browser method"""
    logger.info(f"Testing browser-based fetch for URL: {url}")
    start_time = time.time()
    
    try:
        # Import the browser fetch function
        from news_updater.news_app.browser_fetch import _fetch_with_browser
        
        logger.info(f"Calling _fetch_with_browser for {url}")
        content = _fetch_with_browser(url)
        
        elapsed_time = time.time() - start_time
        logger.info(f"Browser fetch completed in {elapsed_time:.2f} seconds")
        
        return {
            "success": True,
            "method": "browser",
            "content_length": len(content),
            "elapsed_time": elapsed_time,
            "content": content
        }
    
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(f"Browser fetch failed: {str(e)}")
        return {
            "success": False,
            "method": "browser",
            "error": str(e),
            "elapsed_time": elapsed_time,
            "content": None
        }

def test_fetch_url_content(url):
    """Test fetching content using the fetch_url_content function"""
    logger.info(f"Testing fetch_url_content for URL: {url}")
    start_time = time.time()
    
    try:
        # Import the fetch_url_content function
        from news_updater.news_app.tasks import fetch_url_content
        
        logger.info(f"Calling fetch_url_content for {url}")
        content = fetch_url_content(url)
        
        elapsed_time = time.time() - start_time
        logger.info(f"fetch_url_content completed in {elapsed_time:.2f} seconds")
        
        return {
            "success": True,
            "method": "fetch_url_content",
            "content_length": len(content),
            "elapsed_time": elapsed_time,
            "content": content
        }
    
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(f"fetch_url_content failed: {str(e)}")
        return {
            "success": False,
            "method": "fetch_url_content",
            "error": str(e),
            "elapsed_time": elapsed_time,
            "content": None
        }

def analyze_content(content):
    """Analyze the content to determine its quality"""
    if not content:
        return "No content to analyze"
    
    analysis = []
    
    # Check content length
    content_length = len(content)
    analysis.append(f"Content length: {content_length} characters")
    
    # Count paragraphs
    paragraphs = [p for p in content.split('\n') if p.strip()]
    analysis.append(f"Number of paragraphs: {len(paragraphs)}")
    
    # Count words
    words = content.split()
    analysis.append(f"Number of words: {len(words)}")
    
    # Check for HTML fragments
    html_indicators = ["<html", "<body", "<div", "<script", "<style"]
    html_found = [indicator for indicator in html_indicators if indicator in content]
    if html_found:
        analysis.append(f"WARNING: HTML fragments found: {', '.join(html_found)}")
    
    # Check for common error indicators
    error_indicators = [
        "captcha", "robot", "automated access", "detection", "cloudflare",
        "404 not found", "403 forbidden", "access denied", "page not available",
        "loading", "please wait", "enable javascript", "browser not supported"
    ]
    errors_found = [indicator for indicator in error_indicators if indicator in content.lower()]
    if errors_found:
        analysis.append(f"WARNING: Error indicators found: {', '.join(errors_found)}")
    
    # Check for paywall indicators
    paywall_indicators = [
        "subscribe now", "subscription required", "create an account", "sign in to continue",
        "premium content", "members only", "paid subscribers", "register to continue"
    ]
    paywall_found = [indicator for indicator in paywall_indicators if indicator in content.lower()]
    if paywall_found:
        analysis.append(f"WARNING: Paywall indicators found: {', '.join(paywall_found)}")
    
    return "\n".join(analysis)

def main():
    parser = argparse.ArgumentParser(description='Test news fetcher methods')
    parser.add_argument('url', help='URL to fetch')
    parser.add_argument('--method', choices=['all', 'jina', 'requests', 'browser', 'fetch_url_content'], 
                        default='all', help='Fetching method to test')
    parser.add_argument('--output', help='Output file for the fetched content')
    args = parser.parse_args()
    
    results = []
    
    # Test the specified method(s)
    if args.method in ['all', 'jina']:
        result = test_jina_fetch(args.url)
        results.append(result)
        
        print("\n" + "="*80)
        print(f"JINA READER METHOD RESULTS:")
        print(f"Success: {result['success']}")
        print(f"Time: {result['elapsed_time']:.2f} seconds")
        if result['success']:
            print(f"Content length: {result['content_length']} characters")
            print("\nContent analysis:")
            print(analyze_content(result['content']))
            print("\nContent preview (first 500 chars):")
            print(result['content'][:500] + "...")
        else:
            print(f"Error: {result['error']}")
        print("="*80 + "\n")
    
    if args.method in ['all', 'requests']:
        result = test_requests_fetch(args.url)
        results.append(result)
        
        print("\n" + "="*80)
        print(f"REQUESTS METHOD RESULTS:")
        print(f"Success: {result['success']}")
        print(f"Time: {result['elapsed_time']:.2f} seconds")
        if result['success']:
            print(f"Content length: {result['content_length']} characters")
            print("\nContent analysis:")
            print(analyze_content(result['content']))
            print("\nContent preview (first 500 chars):")
            print(result['content'][:500] + "...")
        else:
            print(f"Error: {result['error']}")
        print("="*80 + "\n")
    
    if args.method in ['all', 'browser']:
        result = test_browser_fetch(args.url)
        results.append(result)
        
        print("\n" + "="*80)
        print(f"BROWSER METHOD RESULTS:")
        print(f"Success: {result['success']}")
        print(f"Time: {result['elapsed_time']:.2f} seconds")
        if result['success']:
            print(f"Content length: {result['content_length']} characters")
            print("\nContent analysis:")
            print(analyze_content(result['content']))
            print("\nContent preview (first 500 chars):")
            print(result['content'][:500] + "...")
        else:
            print(f"Error: {result['error']}")
        print("="*80 + "\n")
    
    if args.method in ['all', 'fetch_url_content']:
        result = test_fetch_url_content(args.url)
        results.append(result)
        
        print("\n" + "="*80)
        print(f"FETCH_URL_CONTENT METHOD RESULTS:")
        print(f"Success: {result['success']}")
        print(f"Time: {result['elapsed_time']:.2f} seconds")
        if result['success']:
            print(f"Content length: {result['content_length']} characters")
            print("\nContent analysis:")
            print(analyze_content(result['content']))
            print("\nContent preview (first 500 chars):")
            print(result['content'][:500] + "...")
        else:
            print(f"Error: {result['error']}")
        print("="*80 + "\n")
    
    # Find the best result
    successful_results = [r for r in results if r['success']]
    if successful_results:
        # Sort by content length (longer is usually better)
        best_result = sorted(successful_results, key=lambda x: x['content_length'], reverse=True)[0]
        
        print("\n" + "="*80)
        print(f"BEST METHOD: {best_result['method'].upper()}")
        print(f"Content length: {best_result['content_length']} characters")
        print(f"Time: {best_result['elapsed_time']:.2f} seconds")
        print("="*80 + "\n")
        
        # Save the content to a file if requested
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(best_result['content'])
            print(f"Content saved to {args.output}")
    else:
        print("\nAll methods failed to fetch content.")

if __name__ == "__main__":
    main()
