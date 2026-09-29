"""Typed provider contracts. Implementations live next to the module that uses them."""

import uuid
from datetime import date
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel


class AIHealth(BaseModel):
    provider: str
    status: Literal["disabled", "available", "unavailable"]
    detail: str | None = None


@runtime_checkable
class AIProvider(Protocol):
    """Returns JSON validated against a schema (Phase 4: Ollama).

    `chat_structured` returns (validated output, attempts used, raw text of the final
    reply). It raises app.modules.ai.provider.AIError subclasses with safe messages.
    Grounding checks are the caller's job, so every provider gets them.
    """

    name: str

    async def health(self) -> AIHealth: ...

    async def chat_structured[T: BaseModel](
        self, messages: list[dict[str, str]], schema: type[T], *, max_attempts: int = 2
    ) -> tuple[T, int, str]: ...


class CrawlerProvider(Protocol):
    """Fetches and parses a site within configured limits (Phase 2: local crawler)."""

    async def crawl(self, *, project_id: uuid.UUID, crawl_job_id: uuid.UUID) -> None: ...


class SEOAnalysisProvider(Protocol):
    """Evaluates crawl data and emits findings (Phase 3: rule-based engine)."""

    async def analyse(self, *, crawl_job_id: uuid.UUID) -> None: ...


class ReportProvider(Protocol):
    """Renders reports (Phase 5: local HTML and PDF)."""

    async def render(self, *, crawl_job_id: uuid.UUID, fmt: Literal["html", "pdf"]) -> bytes: ...


# The interfaces below have no implementation yet. They exist so future paid data sources
# plug in without changing callers. Callers must treat "no provider" as "data unavailable"
# and never substitute estimated values.


class KeywordProvider(Protocol):
    async def keyword_metrics(
        self, *, keywords: list[str], locale: str
    ) -> list[dict[str, Any]]: ...


class SERPProvider(Protocol):
    async def search_results(self, *, query: str, locale: str) -> list[dict[str, Any]]: ...


class RankingProvider(Protocol):
    async def rankings(self, *, domain: str, keywords: list[str]) -> list[dict[str, Any]]: ...


class SearchConsoleProvider(Protocol):
    async def performance(
        self, *, site_url: str, start: date, end: date
    ) -> list[dict[str, Any]]: ...


class AnalyticsProvider(Protocol):
    async def page_metrics(
        self, *, site_url: str, start: date, end: date
    ) -> list[dict[str, Any]]: ...


class CMSProvider(Protocol):
    """Publishing requires explicit authorisation and an approved, reversible change."""

    async def fetch_page(self, *, url: str) -> dict[str, Any]: ...

    async def publish_change(self, *, approval_id: uuid.UUID) -> None: ...


class NotificationProvider(Protocol):
    async def send(self, *, recipient: str, subject: str, body: str) -> None: ...
