"""Text generation via OpenRouter (OpenAI-compatible API).

Migrated off Google Gemini after the GOOGLE_API_KEY leak. Summarization and
content preprocessing now run on OpenRouter, with the model configured via
``settings.OPENROUTER_MODEL`` (default ``deepseek/deepseek-v4-flash``).

Embeddings are intentionally NOT handled here: OpenRouter exposes no embeddings
endpoint, so semantic dedup remains a separate concern (see news_app.dedup).
"""
import logging

from django.conf import settings

logger = logging.getLogger('news_app.gemini')  # reuse the existing LLM log channel

OPENROUTER_BASE_URL = 'https://openrouter.ai/api/v1'

_client = None


def available():
    """True when an OpenRouter key is configured; callers degrade gracefully."""
    return bool(getattr(settings, 'OPENROUTER_API_KEY', ''))


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=OPENROUTER_BASE_URL,
        )
    return _client


def chat(prompt, *, temperature=0.3, max_tokens=None):
    """Send a single user prompt and return the model's text response.

    Raises on transport/API errors so callers can apply their existing
    try/except fallbacks (the news pipeline degrades to source links).
    """
    kwargs = {
        'model': getattr(settings, 'OPENROUTER_MODEL', 'deepseek/deepseek-v4-flash'),
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': temperature,
        # OpenRouter routing/attribution headers (optional but recommended).
        'extra_headers': {
            'HTTP-Referer': 'https://news.alexilin.com',
            'X-Title': 'Brew',
        },
    }
    if max_tokens:
        kwargs['max_tokens'] = max_tokens
    response = _get_client().chat.completions.create(**kwargs)
    return response.choices[0].message.content
