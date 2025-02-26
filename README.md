# News Updater

A Django application that uses Claude AI to send regular email news updates.

## Setup Instructions

1. Clone the repository
2. Create and activate a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Configure environment variables:
   - Edit the `.env` file with your settings
   - Make sure to set your Anthropic API key and email settings

5. Run migrations:
   ```
   cd news_updater
   python manage.py migrate
   ```

7. Create a superuser:
   ```
   python manage.py createsuperuser
   ```

8. Set up periodic tasks:
   ```
   python manage.py setup_periodic_tasks
   ```

9. Run the development server:
   ```
   python manage.py runserver
   ```

10. In separate terminal windows, run Celery worker and beat:
    ```
    celery -A news_updater worker -l info
    ```
    
    And in another terminal:
    ```
    celery -A news_updater beat -l info
    ```

## Features

- User registration with email verification
- Create custom news sections with specific sources
- Schedule news updates at preferred times
- Send immediate news updates on demand
- AI-powered news summarization using Claude
- Advanced web scraping with browser simulation
- Headless browser support for JavaScript-heavy sites

## Requirements

- Python 3.8+
- Redis server (for Celery)
- SMTP server for sending emails
- Anthropic API key
- Chrome browser (for headless browser functionality)

## Advanced Content Fetching

The application includes sophisticated content fetching capabilities:

1. **Browser Simulation**: Simulates a real browser with realistic headers, cookies, and browsing patterns to avoid 403 errors and other anti-bot measures.

2. **Headless Browser Support**: Automatically uses a headless Chrome browser for JavaScript-heavy sites that can't be properly scraped with regular HTTP requests.

3. **Smart Content Extraction**: Identifies and extracts the main content from web pages, filtering out ads, navigation, and other non-content elements.

4. **Adaptive Retry Logic**: Implements intelligent retry strategies with exponential backoff and jitter to handle rate limiting and temporary failures.

To test the improved fetching capabilities:

```
python test_improved_fetch.py
```

This will test fetching content from various news sources and report success rates and content previews.
