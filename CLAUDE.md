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
- **Never call `feedparser.parse(url)` with a URL directly** — it has no timeout and will hang on slow sites. Always fetch with `requests.get(url, timeout=...)` first, then pass the content to `feedparser.parse(response.content)`

## Frontend / Templates
- **Base template**: `templates/base.html` — loads Bootstrap 5, Bootstrap Icons, Google Fonts (Inter), custom `static/css/style.css`
- **Custom CSS**: `static/css/style.css` — design system with CSS custom properties, indigo primary (`#4f46e5`)
- `base.html` uses `{% load static %}` at top for the CSS link
- **Navbar**: uses class `navbar-custom` (dark gradient), has brand icon, active link detection via `request.resolver_match.url_name`
- **Footer**: `{{ year }}` context variable expected in footer — if it shows blank, a context processor may be needed
- **Auth pages** (login, signup, verify_email, password_reset*): use `auth-card-wrapper` + `auth-card` classes for centered card layout with `auth-icon-circle` header
- **Dashboard sections**: styled with `section-item` class (left accent border), drag handle uses `bi-grip-vertical` (Bootstrap Icons), SortableJS handle selector is `.bi-grip-vertical`
- **News history cards**: use `news-card` class with `confidence-high/medium/low` modifier for left border color; sources rendered as `source-pill` links
- **Form pages** (add/edit section): card with `p-4` body, icon in heading, no separate card-header
- **Delete page**: uses `delete-warning-card` class with `delete-warning-icon` circle

## Static Files
- `STATICFILES_DIRS` = `[os.path.join(BASE_DIR, 'static')]` → picks up `news_updater/static/`
- `STATIC_ROOT` = `news_updater/staticfiles/` — run `python3 manage.py collectstatic --noinput` after any static file changes
- Bootstrap Icons loaded globally via CDN in `base.html` — use `bi bi-*` classes, NOT Font Awesome `fas fa-*`
- Font Awesome is only loaded on dashboard page via JS (for SortableJS compatibility) — don't rely on it elsewhere

## Template Gotchas
- Badge classes must be BS5: `bg-success`, `bg-warning`, `bg-danger`, `bg-secondary` — NOT BS4 `badge-success` etc.
- BS4 margin/spacing classes (`ml-2`, `mr-2`) should be BS5 (`ms-2`, `me-2`)
- `form_tags` templatetag library provides `add_class` filter — used in login, signup, and form templates
- Template validation: `from django.template.loader import get_template; get_template('name.html')` to check for parse errors

## Python Environment
- Use `python3` not `python` (python not on PATH)
- **Venv at `/var/www/news/venv/`** — always use `/var/www/news/venv/bin/pip` to install packages, NOT bare `pip`/`pip3` (which installs to system Python at `/usr`)
- Requirements in `/var/www/news/requirements.txt`

## Git
- Remote is HTTPS (`https://github.com/payalnik/news.git`)
- **Always git commit and push after completing changes** — commit with a clear message, then push to origin/main
