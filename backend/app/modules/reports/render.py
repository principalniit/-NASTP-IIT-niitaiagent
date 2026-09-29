"""Turns report data into a self-contained HTML document.

Crawled text is untrusted, so the template is rendered with autoescaping. The document
loads nothing from the network: styles are inline and the logo is fetched once, through
the crawler's SSRF guard, and embedded as a data URI.
"""

import asyncio
import base64
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.modules.crawler.url_safety import BlockedDestinationError, GuardedTransport, SafetyPolicy
from app.modules.reports.builder import executive_summary

logger = logging.getLogger(__name__)

LOGO_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
LOGO_MAX_BYTES = 512_000
# The whole download, not each read: a server sending one byte at a time must not hold
# the worker, which serves every organisation.
LOGO_TOTAL_SECONDS = 10.0


def _looks_like(kind: str, body: bytes) -> bool:
    """The file's own signature matches its declared image type."""
    if kind == "image/png":
        return body.startswith(b"\x89PNG\r\n\x1a\n")
    if kind == "image/jpeg":
        return body.startswith(b"\xff\xd8\xff")
    if kind == "image/gif":
        return body.startswith((b"GIF87a", b"GIF89a"))
    return body[:4] == b"RIFF" and body[8:12] == b"WEBP"


DEFAULT_COLOUR = "#1d4ed8"
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=True,
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (KeyError, ValueError):
        return ZoneInfo("UTC")


def format_datetime(value: str | None, timezone: str) -> str:
    if not value:
        return "not recorded"
    moment = datetime.fromisoformat(value).astimezone(_zone(timezone))
    return f"{moment.day} {moment:%B %Y, %H:%M} ({timezone})"


def finalise(data: dict[str, Any]) -> dict[str, Any]:
    """Add the labels and the rule-written summary that depend on the organisation's zone."""
    meta = data["meta"]
    meta["crawl_finished_label"] = format_datetime(meta["crawl_finished_at"], meta["timezone"])
    data["executive_summary"] = executive_summary(data)
    colour = data["branding"].get("primary_colour") or ""
    data["branding"]["primary_colour"] = colour if _HEX.match(colour) else DEFAULT_COLOUR
    return data


async def fetch_logo(url: str | None) -> str | None:
    """The organisation logo as a data URI, or None. Fetched through the SSRF guard."""
    if not url or not url.startswith("https://"):
        return None
    transport = GuardedTransport(SafetyPolicy.from_settings())
    try:
        async with (
            asyncio.timeout(LOGO_TOTAL_SECONDS),
            httpx.AsyncClient(transport=transport, timeout=5.0, follow_redirects=False) as client,
            # Uncompressed only, so the size cap applies to what is actually held in memory.
            client.stream("GET", url, headers={"Accept-Encoding": "identity"}) as response,
        ):
            kind = response.headers.get("content-type", "").split(";")[0].strip().lower()
            encoding = response.headers.get("content-encoding", "identity").strip().lower()
            if response.status_code != 200 or kind not in LOGO_TYPES or encoding != "identity":
                return None
            body = b""
            async for chunk in response.aiter_raw():
                body += chunk
                if len(body) > LOGO_MAX_BYTES:
                    return None
        if not _looks_like(kind, body):
            return None
        return f"data:{kind};base64,{base64.b64encode(body).decode()}"
    except (TimeoutError, httpx.HTTPError, BlockedDestinationError, OSError):
        logger.info("Report logo could not be fetched", extra={"url": url})
        return None


def render_html(data: dict[str, Any], logo: str | None) -> str:
    tz = data["meta"]["timezone"]
    template = _env.get_template("report.html.j2")
    return template.render(
        d=data,
        logo=logo,
        when=lambda value: format_datetime(value, tz),
        score=lambda value: "not scored" if value is None else f"{value:.0f}",
    )
