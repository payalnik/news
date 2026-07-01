"""Lightweight, dependency-free rate limiting backed by the Django cache.

Used to protect unauthenticated, email-sending endpoints (signup, resend
verification) from the automated abuse that flooded the user table with
unverified accounts. Backed by Redis in production (see CACHES in settings),
so counters are shared across gunicorn workers.

Fails OPEN on cache errors: a Redis hiccup must not lock real users out of
signing up. The cap is a spam control, not an auth boundary.
"""
import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)


def client_ip(request):
    """Best-effort client IP, honoring the proxy header set by nginx.

    X-Forwarded-For is a client-supplied header, so the left-most entry can be
    spoofed; it is good enough for coarse spam throttling, not for auth.
    """
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '') or 'unknown'


def rate_limited(key, limit, window_seconds):
    """Return True if ``key`` has already reached ``limit`` hits in the window.

    Counts this call as a hit when it returns False. The window is a fixed
    bucket anchored at the first hit (cheap; good enough for abuse control).
    """
    bucket = f'rl:{key}'
    try:
        count = cache.get(bucket)
        if count is None:
            cache.set(bucket, 1, window_seconds)
            return False
        if count >= limit:
            return True
        try:
            cache.incr(bucket)
        except ValueError:
            # Key expired between get and incr — restart the window.
            cache.set(bucket, 1, window_seconds)
        return False
    except Exception as e:  # noqa: BLE001 - never block signups on cache failure
        logger.warning(f'Rate-limit cache unavailable, failing open: {e}')
        return False
