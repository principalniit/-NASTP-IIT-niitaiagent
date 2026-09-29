"""Rule base class. A rule is a small, pure, deterministic check over AnalysisContext."""

from collections.abc import Iterable
from typing import Any, ClassVar

from app.modules.seo.context import AnalysisContext, PageData, group_subject
from app.modules.seo.findings import Confidence, Effort, Finding, Scope
from app.modules.seo.models import Category, Severity


class Rule:
    id: ClassVar[str]
    category: ClassVar[Category]
    severity: ClassVar[Severity]
    title: ClassVar[str]
    description: ClassVar[str]
    recommendation: ClassVar[str]
    confidence: ClassVar[Confidence] = "high"
    effort: ClassVar[Effort] = "low"
    auto_fix_eligible: ClassVar[bool] = False

    def evaluate(self, ctx: AnalysisContext) -> Iterable[Finding]:
        raise NotImplementedError

    # -- helpers --------------------------------------------------------------

    def page_finding(
        self,
        page: PageData,
        evidence: dict[str, Any],
        *,
        severity: Severity | None = None,
        title: str | None = None,
        description: str | None = None,
        recommendation: str | None = None,
    ) -> Finding:
        return self._make(
            "page",
            group_subject(page.url),
            [page.url],
            1,
            evidence,
            severity,
            title,
            description,
            recommendation,
        )

    def group_finding(
        self,
        subject: str,
        urls: list[str],
        evidence: dict[str, Any],
        *,
        severity: Severity | None = None,
        title: str | None = None,
        description: str | None = None,
        recommendation: str | None = None,
    ) -> Finding:
        return self._make(
            "group",
            subject,
            sorted(urls),
            len(urls),
            evidence,
            severity,
            title,
            description,
            recommendation,
        )

    def site_finding(
        self,
        ctx: AnalysisContext,
        evidence: dict[str, Any],
        *,
        severity: Severity | None = None,
        title: str | None = None,
        description: str | None = None,
        recommendation: str | None = None,
    ) -> Finding:
        count = max(1, len(ctx.pages))
        return self._make(
            "site",
            "site",
            [ctx.root_url],
            count,
            evidence,
            severity,
            title,
            description,
            recommendation,
        )

    def _make(
        self,
        scope: Scope,
        subject: str,
        urls: list[str],
        count: int,
        evidence: dict[str, Any],
        severity: Severity | None,
        title: str | None,
        description: str | None,
        recommendation: str | None,
    ) -> Finding:
        return Finding(
            rule_id=self.id,
            category=self.category,
            severity=severity or self.severity,
            scope=scope,
            subject=subject[:120],
            title=title or self.title,
            description=description or self.description,
            recommendation=recommendation or self.recommendation,
            evidence=evidence,
            affected_urls=urls,
            affected_page_count=count,
            confidence=self.confidence,
            effort=self.effort,
            auto_fix_eligible=self.auto_fix_eligible,
        )

    @classmethod
    def catalogue_entry(cls) -> dict[str, Any]:
        return {
            "id": cls.id,
            "category": cls.category.value,
            "default_severity": cls.severity.value,
            "title": cls.title,
            "description": cls.description,
            "recommendation": cls.recommendation,
            "confidence": cls.confidence,
            "effort": cls.effort,
            "auto_fix_eligible": cls.auto_fix_eligible,
        }


def escalate(ctx: AnalysisContext, page: PageData, base: Severity, raised: Severity) -> Severity:
    """Use the raised severity for the home page and configured important pages."""
    return raised if ctx.is_important(page.url) else base
