"""URL normalisation and static safety checks shared by projects and the crawler.

These checks do not resolve DNS. The crawler (Phase 2) adds resolution-time checks.
"""

import ipaddress
from urllib.parse import urlsplit, urlunsplit

ALLOWED_SCHEMES = {"http", "https"}
BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain", "metadata.google.internal"}
BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".localdomain", ".home.arpa")


class UnsafeURLError(ValueError):
    pass


def is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return is_public_ip(ip.ipv4_mapped)
    return ip.is_global and not ip.is_multicast


def normalise_hostname(host: str) -> str:
    host = host.strip().rstrip(".").lower()
    if not host:
        raise UnsafeURLError("URL must include a hostname")
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise UnsafeURLError("Hostname is not valid") from exc


def normalise_site_url(raw: str) -> tuple[str, str]:
    """Validate a site root URL and return (normalised_url, hostname).

    Rejects non-HTTP schemes, embedded credentials, local hostnames and non-public IP literals.
    """
    raw = raw.strip()
    if "://" not in raw:
        raw = "https://" + raw
    parts = urlsplit(raw)
    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise UnsafeURLError("Only http and https URLs are allowed")
    if parts.username or parts.password:
        raise UnsafeURLError("URLs must not contain credentials")
    if parts.hostname is None:
        raise UnsafeURLError("URL must include a hostname")
    try:
        ip = ipaddress.ip_address(parts.hostname)
    except ValueError:
        host = normalise_hostname(parts.hostname)
        if host in BLOCKED_HOSTNAMES or host.endswith(BLOCKED_SUFFIXES):
            raise UnsafeURLError("Local and internal hostnames are not allowed") from None
        if "." not in host:
            raise UnsafeURLError("Hostname must be a fully qualified domain") from None
    else:
        if not is_public_ip(ip):
            raise UnsafeURLError("Private, loopback and reserved addresses are not allowed")
        host = f"[{ip.compressed}]" if ip.version == 6 else ip.compressed
    try:
        port = parts.port
    except ValueError as exc:
        raise UnsafeURLError("Port is not valid") from exc
    default_port = 443 if scheme == "https" else 80
    netloc = host if port in (None, default_port) else f"{host}:{port}"
    path = parts.path or "/"
    return urlunsplit((scheme, netloc, path, parts.query, "")), host
