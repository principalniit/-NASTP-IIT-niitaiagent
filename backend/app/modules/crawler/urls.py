"""URL handling for discovered links: normalisation, scope and exclusions."""

import fnmatch
from urllib.parse import urljoin, urlsplit, urlunsplit

from app.core.urls import UnsafeURLError, normalise_hostname

MAX_URL_LENGTH = 2048
SKIPPED_SCHEMES = ("javascript:", "mailto:", "tel:", "data:", "ftp:", "file:", "sms:")


def normalise_url(raw: str, base: str | None = None) -> str | None:
    """Return a canonical absolute http(s) URL, or None if the link is not crawlable.

    Lower-cases scheme and host, removes default ports and fragments, resolves dot
    segments and keeps the query unchanged (reordering could change meaning).
    """
    raw = raw.strip()
    if not raw or raw.lower().startswith(SKIPPED_SCHEMES):
        return None
    if raw.endswith("://") or raw.lower() in ("http:", "https:"):
        return None  # a scheme with no host is invalid, not a link to the base page
    absolute = urljoin(base, raw) if base else raw
    try:
        parts = urlsplit(absolute)
        port = parts.port
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https") or not parts.hostname:
        return None
    if parts.username or parts.password:
        return None
    try:
        host = normalise_hostname(parts.hostname)
    except UnsafeURLError:
        return None
    if ":" in host:
        host = f"[{host}]"
    default = 443 if scheme == "https" else 80
    netloc = host if port in (None, default) else f"{host}:{port}"
    path = parts.path or "/"
    if "/." in path:
        path = urlsplit(urljoin(f"{scheme}://{netloc}/", path)).path
    url = urlunsplit((scheme, netloc, path, parts.query, ""))
    return url if len(url) <= MAX_URL_LENGTH else None


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def www_twin(host: str) -> str | None:
    """The same site's other common name: www.example.org for example.org and back.

    Sites usually redirect one to the other, and link to either, so both belong to the
    crawl. None for addresses without a domain name (IP addresses, localhost).
    """
    if "." not in host or host.replace(".", "").isdigit() or ":" in host:
        return None
    return host.removeprefix("www.") if host.startswith("www.") else f"www.{host}"


def port_of(url: str) -> int:
    parts = urlsplit(url)
    return parts.port or (443 if parts.scheme == "https" else 80)


def path_with_query(url: str) -> str:
    parts = urlsplit(url)
    return (parts.path or "/") + (f"?{parts.query}" if parts.query else "")


def is_excluded(url: str, patterns: list[str]) -> bool:
    path = urlsplit(url).path or "/"
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)
