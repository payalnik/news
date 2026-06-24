# News Updater Project Memory

## Project Structure
- **Product name is "Brew"** (tagline "News, brewed your way"; coffee-cup icon `bi-cup-hot`). The user-facing brand is Brew everywhere (navbar, titles, footer, email subject "Your Brew · {date}", digest h1 "Your Brew"). The Django project/package/dir is still `news_updater` and the app is `news_app` — those are internal, don't rename them.
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
- RSS discovery order: `<link rel="alternate">` tags first (authoritative), then common paths as fallback with early exit after 3 misses
- Skip `/comments/` feed URLs — they contain user comments, not articles (e.g. mercurynews.com)

## Deduplication (avoiding repeated news)
- Logic lives in `news_app/dedup.py` (ORM-free; operates on plain dicts so the same code dedupes both stored items and not-yet-saved items in the current batch)
- Signals applied cheapest/strongest first: (1) exact `content_hash`, (2) shared normalized source URL, (3) semantic similarity via Gemini embeddings, (4) lexical headline/detail Jaccard fallback
- `NewsItem` has `content_hash` (auto-filled in `save()`) and `embedding` (JSON list of floats) — see migration `0006`
- `normalize_url()` strips scheme/`www.`/tracking params/trailing slash so http/https + utm variants collapse — URL match is the most reliable repeat signal
- Embeddings: `client.models.embed_content(model=settings.DEDUP_EMBEDDING_MODEL, contents=..., config=EmbedContentConfig(task_type='SEMANTIC_SIMILARITY', output_dimensionality=settings.DEDUP_EMBEDDING_DIM))`; `embed_text()` returns `None` on any failure and the pipeline degrades to lexical dedup
- All thresholds/windows are settings: `DEDUP_LOOKBACK_DAYS`, `DEDUP_MAX_RECENT_ITEMS`, `DEDUP_SEMANTIC_THRESHOLD`, `DEDUP_HEADLINE_THRESHOLD`, `DEDUP_EMBEDDING_MODEL`, `DEDUP_EMBEDDING_DIM`, `DEDUP_BACKFILL_EMBEDDINGS`
- The LLM-context window (previously-reported items in the prompt) and the post-generation filter window are now BOTH `DEDUP_LOOKBACK_DAYS` — keep them aligned
- Prompt now lists prior items as `headline [sources: domain1, domain2]` for a stronger "already covered" signal
- Dedup also runs WITHIN a single batch (`batch_prev`) so two generated items in one run can't duplicate each other
- Per-section dedup metrics are logged: `Dedup for section '...': N generated, M duplicates filtered, K kept`
- `is_similar_to()` on `NewsItem` is now a thin wrapper over `dedup.lexical_similar()` (stop words stripped from headlines too; threshold defaults to `DEDUP_HEADLINE_THRESHOLD`)

## Task reliability & performance (send_news_update)
- **Persist-after-send**: `NewsItem`s are accumulated in `pending_news_items` and only `.save()`d AFTER `email.send()` succeeds (wrapped in `transaction.atomic()`). Never save items before the email goes out — otherwise a send failure makes the news vanish forever via the dedup filter on the next run
- **Parallel source fetches**: a section's sources are fetched concurrently via `ThreadPoolExecutor` (`settings.NEWS_FETCH_CONCURRENCY`, default 4). Playwright's sync API is NOT thread-safe across a shared session, so each parallel fetch passes `browser_session=None` and spins up its own short-lived session (`fetch_with_playwright` creates its own `BrowserSession`). Do NOT share one `BrowserSession` across threads
- Source cap is `settings.NEWS_MAX_SOURCES_PER_SECTION` (default 7), not a hardcoded 7
- **Batched embeddings**: use `dedup.embed_texts(client, [...])` (one API call for many texts) for both candidate items and the recent-item backfill — not per-item `embed_text` in a loop
- SQLite is in WAL mode for concurrent worker/gunicorn access: `OPTIONS={'timeout': 20}` in settings + PRAGMAs (`journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout`) applied via the `connection_created` signal in `news_app/apps.py` (the sqlite3 backend ignores `init_command`)

## Tests
- Test suite in `news_app/tests.py`: dedup unit tests (pure functions) + `send_news_update` integration tests (mocked Gemini client + fetch + locmem email)
- Run them via the `.env`/PYTHONPATH workaround documented in project memory — **`PYTHONPATH=/var/www/news`** (NOT `.../news_updater`, which breaks discovery because the repo root is itself a package named `news_updater`) and label `news_app.tests`

## Frontend / Templates
- **Base template**: `templates/base.html` — loads Bootstrap 5, Bootstrap Icons, Google Fonts (Inter), custom `static/css/style.css`
- **Custom CSS**: `static/css/style.css` — design system with CSS custom properties, indigo primary (`#4f46e5`)
- `base.html` uses `{% load static %}` at top for the CSS link
- **Navbar**: uses class `navbar-custom` (dark gradient), has brand icon, active link detection via `request.resolver_match.url_name`
- **Footer**: uses `{% now "Y" %}` for the year (no context variable needed)
- **Auth pages** (login, signup, verify_email, password_reset*): use `auth-card-wrapper` + `auth-card` classes for centered card layout with `auth-icon-circle` header
- **Dashboard sections**: styled with `section-item` class (left accent border); the SortableJS drag handle is `.drag-handle` (an `<i class="bi bi-grip-vertical drag-handle">`). Sources shown as `.source-chip` (favicon via `google.com/s2/favicons?domain=`, domain from `NewsSection.get_source_domains()`); instructions truncated with `|truncatechars:140`
- **Delivery schedule**: add-able dropdowns, NOT checkboxes/accordions. Each chosen time is a `<select name="time_slots">` (options from `views.TIME_CHOICES`, value `HH:MM` 24h, label 12h); JS clones `#time-slot-template` to add rows and removes via `.btn-remove-slot`. View reads `request.POST.getlist('time_slots')`, validates against `views.VALID_TIME_VALUES`. There is no `TimeSlotForm` anymore
- **News history cards**: `news-card` (neutral left border); headline `.news-headline`, body `.news-details`, section label `.news-section-tag`; sources as `source-pill` links. **No `confidence`** — that field/UI was removed entirely (migration 0007); LLM self-confidence was unused and poorly calibrated. Don't reintroduce it
- Timezone: `base.html` sets a `client_timezone` cookie AND injects a hidden input into `form[action*="time-slots"]` (note the hyphen — must match the `/update-time-slots/` URL); the view falls back cookie → server tz
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
- `/var/www/news/.env` is owned by `www-data` and not readable by the `payalnik` user, so `manage.py` fails at `load_dotenv()` with `PermissionError`. To run management commands locally, stub it: `python3 -c "import dotenv; dotenv.load_dotenv=lambda *a,**k:False; import django; django.setup(); ..."` with `SECRET_KEY`/`GOOGLE_API_KEY` set inline (DB is sqlite, `payalnik` is in the `www-data` group so has rw on `db.sqlite3` + its dir)

## Workflow Rules
- **Always update CLAUDE.md with what you learned** after completing a task — document new patterns, gotchas, or conventions discovered
- **Always git commit and push after completing changes** — commit with a clear message, then push to origin/main

## Git
- Remote is HTTPS (`https://github.com/payalnik/news.git`)
