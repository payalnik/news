# News Updater

A Django application that uses Google Gemini AI to send regular email news updates.

## Project Structure

The Django project is located in the `news_updater` directory. All Django commands should be run from within this directory.

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
   - Make sure to set your Google API key and email settings

5. Run migrations:
   ```
   cd news_updater
   python manage.py migrate
   ```

6. Create a superuser:
   ```
   python manage.py createsuperuser
   ```

7. Set up periodic tasks:
   ```
   python manage.py setup_periodic_tasks
   ```

8. Run the development server:
   ```
   python manage.py runserver
   ```

9. In separate terminal windows, run Celery worker and beat:
   ```
   cd news_updater
   celery -A news_updater worker -l info
   ```
   
   And in another terminal:
   ```
   cd news_updater
   celery -A news_updater beat -l info
   ```

## Quick Start

For convenience, you can use the provided startup scripts:

- `run_news_updater.sh` - Starts all services using tmux
- `run_news_updater_simple.sh` - Starts all services using screen or background processes

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
