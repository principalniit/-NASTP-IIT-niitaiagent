"""Per-request metadata used for audit logging and rate limiting."""

from dataclasses import dataclass

from fastapi import Request

from app.core.config import get_settings


@dataclass(frozen=True)
class RequestMeta:
    ip: str | None
    user_agent: str | None


def client_ip(request: Request) -> str | None:
    if get_settings().trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()[:64]
    return request.client.host if request.client else None


def get_request_meta(request: Request) -> RequestMeta:
    ua = request.headers.get("user-agent")
    return RequestMeta(ip=client_ip(request), user_agent=ua[:300] if ua else None)
