"""HTTP fetching for the crawler.

Redirects are followed manually so that every hop is scope-checked here and
SSRF-checked by the guarded transport. Response bodies are read with a size cap that
applies after decompression, which also defeats compression bombs.
"""

import ssl
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.modules.crawler.url_safety import (
    BlockedDestinationError,
    GuardedTransport,
    Resolver,
    SafetyPolicy,
    system_resolve,
)
from app.modules.crawler.urls import normalise_url

REDIRECT_CODES = {301, 302, 303, 307, 308}
HTML_TYPES = ("text/html", "application/xhtml+xml")


@dataclass
class FetchResult:
    url: str
    outcome: (
        str  # ok | not_modified | blocked_destination | redirect_out_of_scope | too_large | error
    )
    final_url: str | None = None
    status_code: int | None = None
    redirect_chain: list[dict[str, Any]] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes | None = None
    elapsed_ms: int | None = None
    error: str | None = None

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "").split(";", 1)[0].strip().lower()

    @property
    def is_html(self) -> bool:
        return self.content_type in HTML_TYPES


KEPT_HEADERS = (
    "content-type",
    "content-length",
    "x-robots-tag",
    "etag",
    "last-modified",
    "location",
)


def _causes(exc: BaseException) -> list[BaseException]:
    found: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and current not in found:
        found.append(current)
        current = current.__cause__ or current.__context__
    return found


def describe_error(exc: BaseException) -> str:
    """A plain explanation of a failed request, for crawl notes and page errors."""
    causes = _causes(exc)
    for cause in causes:
        if isinstance(cause, ssl.SSLCertVerificationError):
            reason = cause.verify_message or "verification failed"
            if "local issuer" in reason:
                reason += "; the server does not send its full certificate chain"
            return f"The site's security certificate could not be verified ({reason})"
    if any(isinstance(c, ssl.SSLError) for c in causes):
        return "The secure (TLS) connection to the server failed"
    text = " ".join(str(c) for c in causes).lower()
    if "could not resolve" in text:
        return "The site's name could not be found (DNS)"
    if any(isinstance(c, ConnectionRefusedError) for c in causes) or "refused" in text:
        return "The server refused the connection"
    if any(isinstance(c, ConnectionResetError) for c in causes) or "reset" in text:
        return "The server closed the connection"
    if isinstance(exc, httpx.RemoteProtocolError):
        return "The server sent an invalid or empty response"
    if isinstance(exc, httpx.ConnectError):
        return "Could not connect to the server"
    return f"Request failed: {type(exc).__name__}"


class Fetcher:
    def __init__(
        self,
        *,
        user_agent: str,
        timeout_seconds: float,
        max_bytes: int,
        max_redirects: int,
        policy: SafetyPolicy,
        resolver: Resolver = system_resolve,
        max_connections: int = 10,
    ) -> None:
        self.user_agent = user_agent
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        self.transport = GuardedTransport(policy, resolver, max_connections=max_connections)
        self.client = httpx.AsyncClient(
            transport=self.transport,
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(timeout_seconds),
            headers={
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.5",
                "Accept-Encoding": "gzip, deflate",
            },
        )

    async def aclose(self) -> None:
        await self.client.aclose()

    async def fetch(
        self,
        url: str,
        *,
        in_scope: Callable[[str], bool],
        read_body: Callable[[str], bool] = lambda content_type: content_type in HTML_TYPES,
        conditional: dict[str, str] | None = None,
        max_bytes: int | None = None,
        before_request: Callable[[str], Awaitable[None]] | None = None,
    ) -> FetchResult:
        """Fetch url, following in-scope redirects.

        before_request is awaited before every request, including each redirect hop, so
        per-host politeness delays apply to redirects too.
        """
        limit = max_bytes or self.max_bytes
        result = FetchResult(url=url, outcome="error")
        current = url
        for hop in range(self.max_redirects + 1):
            headers = conditional if hop == 0 and conditional else None
            if before_request is not None:
                await before_request(current)
            started = time.perf_counter()
            try:
                async with self.client.stream("GET", current, headers=headers) as response:
                    elapsed = int((time.perf_counter() - started) * 1000)
                    kept = {k: response.headers[k] for k in KEPT_HEADERS if k in response.headers}
                    location = kept.get("location")
                    if response.status_code in REDIRECT_CODES and location:
                        target = normalise_url(location, current)
                        result.redirect_chain.append(
                            {
                                "url": current,
                                "status_code": response.status_code,
                                "elapsed_ms": elapsed,
                            }
                        )
                        if target is None:
                            result.error = "Redirect to an unsupported or invalid URL"
                            return result
                        if not in_scope(target):
                            result.outcome = "redirect_out_of_scope"
                            result.final_url = target
                            return result
                        current = target
                        continue
                    result.final_url = current
                    result.status_code = response.status_code
                    result.headers = kept
                    result.elapsed_ms = elapsed
                    if response.status_code == 304:
                        result.outcome = "not_modified"
                        return result
                    if not read_body(result.content_type):
                        result.outcome = "ok"
                        return result
                    declared = kept.get("content-length", "")
                    if declared.isdigit() and int(declared) > limit:
                        result.outcome = "too_large"
                        return result
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > limit:
                            result.outcome = "too_large"
                            return result
                        chunks.append(chunk)
                    result.body = b"".join(chunks)
                    result.outcome = "ok"
                    return result
            except BlockedDestinationError as exc:
                result.outcome = "blocked_destination"
                result.final_url = current
                result.error = str(exc)
                return result
            except httpx.TimeoutException:
                result.error = "Request timed out"
                return result
            except (httpx.HTTPError, httpx.InvalidURL) as exc:
                result.error = describe_error(exc)
                return result
        result.error = f"More than {self.max_redirects} redirects"
        return result
