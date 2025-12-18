
import logging
import sys
import os

# Add the project root to the python path
sys.path.append(os.getcwd())

# Configure logging
logging.basicConfig(level=logging.INFO)

from news_updater.news_app.browser_fetch import _fetch_with_browser

def test_url(url):
    print(f"Testing URL: {url}")
    content = _fetch_with_browser(url)
    if content:
        print(f"Success! Content length: {len(content)}")
        print("First 500 chars:")
        print(content[:500])
        print("-" * 50)
    else:
        print("Failed to fetch content.")

if __name__ == "__main__":
    axios_url = "https://www.axios.com/2024/05/07/israel-hamas-ceasefire-deal-rafah-operation" 
    wired_url = "https://www.wired.com/story/rabbit-r1-android-app-code/" # Example wired article

    print("Testing Axios...")
    test_url(axios_url)

    print("\nTesting Wired...")
    test_url(wired_url)

