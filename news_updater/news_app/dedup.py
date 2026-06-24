"""Deduplication helpers for news items.

The goal is to stop the newsletter from re-reporting stories that were already
sent. We combine several signals, cheapest/strongest first:

  1. exact content hash      -> same headline+details verbatim
  2. shared source URL       -> two items cite the same article (deterministic)
  3. semantic similarity     -> same story, reworded (Gemini embeddings)
  4. lexical headline overlap -> last-resort fallback when embeddings unavailable

This module is intentionally ORM-free: callers pass plain dicts so the same
logic works for both stored items and not-yet-saved items in the current batch.
"""
import hashlib
import logging
import math
import re
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

from django.conf import settings

logger = logging.getLogger('news_app.dedup')

# Query params that never identify the article itself.
_TRACKING_PARAMS = {
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    'fbclid', 'gclid', 'mc_cid', 'mc_eid', 'ref', 'ref_src', 'cmpid',
    'icid', 'ito', 'igshid', 's', 'spm',
}

_STOP_WORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'of', 'for',
    'with', 'by', 'is', 'are', 'was', 'were', 'that', 'this', 'it', 'has',
    'have', 'had', 'be', 'been', 'from', 'as', 'after', 'amid', 'over', 'new',
    'says', 'say', 'will',
}


def normalize_url(url):
    """Return a canonical form of ``url`` for equality comparison.

    Lowercases the host, drops ``www.``, the scheme, fragments and tracking
    query params, and strips a trailing slash. Returns ``''`` on failure.
    """
    if not url:
        return ''
    try:
        parsed = urlparse(url.strip())
        host = (parsed.netloc or '').lower()
        if host.startswith('www.'):
            host = host[4:]
        path = parsed.path.rstrip('/')
        kept = [(k, v) for k, v in parse_qsl(parsed.query)
                if k.lower() not in _TRACKING_PARAMS]
        query = urlencode(sorted(kept))
        # scheme dropped so http/https variants collapse together
        return urlunparse(('', host, path, '', query, ''))
    except Exception:
        return ''


def normalized_source_urls(sources):
    """Build a set of normalized URLs from a list of ``{"url", "title"}`` dicts."""
    out = set()
    for source in sources or []:
        url = source.get('url') if isinstance(source, dict) else None
        norm = normalize_url(url)
        if norm:
            out.add(norm)
    return out


def content_hash_for(headline, details):
    """Stable hash of the normalized headline+details for exact-match dedup."""
    norm = re.sub(r'\s+', ' ', f"{headline or ''} {details or ''}".lower()).strip()
    return hashlib.sha256(norm.encode('utf-8')).hexdigest()


def _tokens(text):
    return {w for w in re.sub(r'[^\w\s]', ' ', (text or '').lower()).split()
            if w and w not in _STOP_WORDS}


def lexical_similar(headline_a, details_a, headline_b, details_b, threshold):
    """Lexical fallback: Jaccard overlap on headlines, backed by details.

    Stop words are stripped from headlines too (the old version only stripped
    them from details, which inflated the union and hid real duplicates).
    """
    if (headline_a or '').lower().strip() == (headline_b or '').lower().strip():
        return True

    ha, hb = _tokens(headline_a), _tokens(headline_b)
    if not ha or not hb:
        return False

    headline_sim = len(ha & hb) / len(ha | hb)
    if headline_sim >= threshold:
        return True

    # Moderately similar headlines: confirm with a details comparison to catch
    # the same event reported under a different headline.
    if headline_sim >= 0.3 and details_a and details_b:
        da, db = _tokens(details_a), _tokens(details_b)
        if da and db:
            detail_sim = len(da & db) / len(da | db)
            if 0.6 * headline_sim + 0.4 * detail_sim >= 0.5:
                return True
    return False


def cosine(a, b):
    """Cosine similarity of two equal-length vectors; 0.0 if either is empty."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def embed_text(client, text):
    """Return an embedding vector for ``text`` (or ``None`` on any failure).

    Best-effort: callers degrade to lexical dedup when this returns ``None``.
    """
    if client is None or not text:
        return None
    try:
        from google.genai import types
        resp = client.models.embed_content(
            model=settings.DEDUP_EMBEDDING_MODEL,
            contents=text[:8000],
            config=types.EmbedContentConfig(
                task_type='SEMANTIC_SIMILARITY',
                output_dimensionality=settings.DEDUP_EMBEDDING_DIM,
            ),
        )
        if resp.embeddings and resp.embeddings[0].values:
            return list(resp.embeddings[0].values)
    except Exception as e:
        logger.warning(f"Embedding failed, falling back to lexical dedup: {e}")
    return None


def match_reason(candidate, prev, *, semantic_threshold, headline_threshold):
    """Return a short reason string if ``candidate`` duplicates ``prev``, else None.

    Both args are dicts with keys: headline, details, urls (set), hash,
    embedding (list[float] | None).
    """
    if candidate.get('hash') and candidate['hash'] == prev.get('hash'):
        return 'content-hash'

    shared = candidate.get('urls', set()) & prev.get('urls', set())
    if shared:
        return f"shared-url:{next(iter(shared))}"

    ce, pe = candidate.get('embedding'), prev.get('embedding')
    if ce and pe:
        sim = cosine(ce, pe)
        if sim >= semantic_threshold:
            return f"semantic:{sim:.2f}"

    if lexical_similar(candidate.get('headline'), candidate.get('details'),
                       prev.get('headline'), prev.get('details'),
                       headline_threshold):
        return 'lexical'
    return None


def find_duplicate(candidate, previous_items, *, semantic_threshold, headline_threshold):
    """Return ``(prev_item, reason)`` for the first match, or ``(None, None)``."""
    for prev in previous_items:
        reason = match_reason(
            candidate, prev,
            semantic_threshold=semantic_threshold,
            headline_threshold=headline_threshold,
        )
        if reason:
            return prev, reason
    return None, None
