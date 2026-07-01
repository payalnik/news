"""SSRF guard + size-capped HTTP fetch for user-supplied source URLs.

Every URL a user adds as a section "source" is fetched server-side (RSS,
requests, and a headless browser). Without validation this is a Server-Side
Request Forgery sink: a source like ``file:///var/www/news/.env``,
``http://169.254.169.254/…`` (cloud metadata), or ``http://127.0.0.1:6379/``
(the local Redis broker) would be fetched and its contents emailed back to the
attacker. This module is the single chokepoint that closes that class:

* ``validate_public_url`` — scheme allowlist (http/https only) + DNS resolution
  with rejection of any address that is not globally routable (loopback,
  private RFC-1918, link-local incl. 169.254.0.0/16, CGNAT, reserved,
  multicast, IPv4-mapped IPv6 forms).
* ``safe_get`` — validates, disables automatic redirects and re-validates every
  redirect hop (so a public URL cannot 302 you into an internal host), and
  streams the body with a hard *decompressed* size cap so a gzip bomb cannot
  OOM the worker.

Residual: a determined attacker can still race DNS between validation and the
socket connect (DNS rebinding). The window is small and every redirect hop is
re-resolved; fully closing it would require pinning the connection to the
validated IP (which breaks TLS SNI/cert validation for HTTPS). The exploited
vectors (file://, direct internal address, redirect-to-internal, decompression
bomb) are all closed here.
"""
import ipaddress
import logging
import socket
from urllib.parse import urljoin, urlparse

import requests

logger = logging.getLogger('news_app.fetch')

ALLOWED_SCHEMES = {'http', 'https'}
# Hard cap on decompressed response size (defends against gzip/deflate bombs).
MAX_FETCH_BYTES = 10 * 1024 * 1024  # 10 MiB
MAX_REDIRECTS = 5
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class UnsafeURLError(Exception):
    """Raised when a URL is disallowed (bad scheme or non-public address)."""


def _ip_is_blocked(ip_str):
    """True if ``ip_str`` is anything other than a globally-routable address."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    # Unwrap ::ffff:a.b.c.d style IPv4-mapped IPv6 so the v4 rules apply.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    # is_global is False for private, loopback, link-local, CGNAT, reserved,
    # and unspecified ranges — exactly the set we must refuse to fetch.
    return (not ip.is_global) or ip.is_multicast


def validate_public_url(url):
    """Validate ``url`` for server-side fetching.

    Returns the set of resolved IP strings on success; raises ``UnsafeURLError``
    for a disallowed scheme, an unresolvable host, or a host that resolves to
    any non-public address.
    """
    parsed = urlparse(url)
    scheme = (parsed.scheme or '').lower()
    if scheme not in ALLOWED_SCHEMES:
        raise UnsafeURLError(f'scheme {scheme!r} not allowed for {url!r}')
    host = parsed.hostname
    if not host:
        raise UnsafeURLError(f'missing host in {url!r}')

    port = parsed.port or (443 if scheme == 'https' else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeURLError(f'DNS resolution failed for {host!r}: {exc}')

    ips = {info[4][0] for info in infos}
    if not ips:
        raise UnsafeURLError(f'no addresses resolved for {host!r}')
    for ip in ips:
        if _ip_is_blocked(ip):
            raise UnsafeURLError(f'{host!r} resolves to non-public address {ip}')
    return ips


class SafeResponse:
    """Minimal stand-in for ``requests.Response`` with capped, pre-read content.

    Exposes the attributes the fetch pipeline uses: ``status_code``,
    ``content``, ``text``, ``url``, and ``raise_for_status()``.
    """

    def __init__(self, status_code, content, url, encoding=None):
        self.status_code = status_code
        self.content = content
        self.url = url
        self.encoding = encoding or 'utf-8'

    @property
    def text(self):
        return self.content.decode(self.encoding, errors='replace')

    def raise_for_status(self):
        if 400 <= self.status_code < 600:
            raise requests.exceptions.HTTPError(
                f'{self.status_code} for {self.url}', response=self)


def safe_get(url, *, headers=None, timeout=15, cookies=None, session=None,
             max_bytes=MAX_FETCH_BYTES):
    """SSRF-safe replacement for ``requests.get``.

    Validates every hop, follows redirects manually (re-validating each target),
    and reads at most ``max_bytes`` of *decompressed* body. Raises
    ``UnsafeURLError`` if any hop is disallowed. Other transport errors surface
    as the usual ``requests`` exceptions so existing callers keep working.
    """
    own_session = session is None
    sess = session or requests.Session()
    current = url
    try:
        for _ in range(MAX_REDIRECTS + 1):
            validate_public_url(current)
            resp = sess.get(current, headers=headers, timeout=timeout,
                            cookies=cookies, allow_redirects=False, stream=True)
            try:
                if resp.status_code in _REDIRECT_STATUSES and resp.headers.get('location'):
                    current = urljoin(current, resp.headers['location'])
                    continue
                # decode_content=True transparently decompresses; the +1 lets us
                # detect (and reject) a body that exceeds the cap.
                body = resp.raw.read(max_bytes + 1, decode_content=True)
                if len(body) > max_bytes:
                    raise UnsafeURLError(
                        f'response from {current} exceeds {max_bytes} byte cap')
                return SafeResponse(resp.status_code, body, current, resp.encoding)
            finally:
                resp.close()
        raise UnsafeURLError(f'too many redirects fetching {url}')
    finally:
        if own_session:
            sess.close()
