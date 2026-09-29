"""The unit of output from a rule. Validation enforces the project principle that every
issue carries evidence and an actionable recommendation."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.modules.seo.models import Category, Severity

Confidence = Literal["high", "medium", "low"]
Effort = Literal["low", "medium", "high"]
Scope = Literal["page", "group", "site"]

MAX_STORED_URLS = 200


class Finding(BaseModel):
    rule_id: str = Field(min_length=3)
    category: Category
    severity: Severity
    scope: Scope
    # Identifies the subject within the rule (a URL, a group hash or "site").
    subject: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=3, max_length=300)
    description: str = Field(min_length=10)
    recommendation: str = Field(min_length=10)
    evidence: dict[str, Any] = Field(min_length=1)
    affected_urls: list[str] = Field(min_length=1)
    affected_page_count: int = Field(ge=1)
    confidence: Confidence
    effort: Effort
    auto_fix_eligible: bool = False

    @property
    def issue_key(self) -> str:
        return f"{self.rule_id}:{self.subject}"[:200]

    @property
    def primary_url(self) -> str | None:
        return self.affected_urls[0] if self.scope == "page" else None
