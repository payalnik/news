# News Updater Project Memory

## Project Structure
- Django app at `/var/www/news/news_updater/`
- Main logic in `news_app/tasks.py` — fetch cascade: RSS → Jina → Requests → Browser
- Browser fetch in `news_app/browser_fetch.py`
- Uses Celery + Redis for task scheduling
- Uses Google Gemini for LLM summarization

## Key Patterns
- `fetch_url_content()` is the main entry point for fetching URLs
- `is_content_suitable_for_llm()` validates scraped content before passing to Gemini
- `JINA_BLOCKLIST` set for domains that return 451 from Jina Reader
- `problematic_sites` list for domains that need browser-first fetch
- `feedparser` used for RSS/Atom feed discovery and parsing

## Python Environment
- Use `python3` not `python` (python not on PATH)
- **Venv at `/var/www/news/venv/`** — always use `/var/www/news/venv/bin/pip` to install packages, NOT bare `pip`/`pip3` (which installs to system Python at `/usr`)
- Requirements in `/var/www/news/requirements.txt`
