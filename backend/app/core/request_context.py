"""Per-request metadata used for audit logging and rate limiting."""

from dataclasses import dataclass

from fastapi import Request

from app.core.config import get_settings


@dataclass(frozen=True)
class RequestMeta:
    ip: str | None
    user_agent: str | None


def client_ip(request: Request) -> str | None:
    """Return the caller's address.

    Behind exactly one trusted reverse proxy (the Next.js server in the standard deployment)
    the proxy appends the real client address to X-Forwarded-For, so the right-most entry is
    the only trustworthy one. Earlier entries can be forged by the client.
    """
    if get_settings().trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            last = forwarded.split(",")[-1].strip()
            if last:
                return last[:64]
    return request.client.host if request.client else None


def get_request_meta(request: Request) -> RequestMeta:
    ua = request.headers.get("user-agent")
    return RequestMeta(ip=client_ip(request), user_agent=ua[:300] if ua else None)
