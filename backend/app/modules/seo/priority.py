"""Issue prioritisation with an explanation of every factor.

priority = (severity + reach + page importance + quick-win bonus) x confidence, 0 to 100.

Severity dominates: each step is worth more than the page-importance bonus, so a high
issue on an ordinary page always outranks a low issue on the home page.
"""

import math
from typing import Any

from app.modules.seo.context import AnalysisContext
from app.modules.seo.findings import Finding

SEVERITY_POINTS = {"critical": 55, "high": 40, "medium": 25, "low": 10, "informational": 2}
EFFORT_POINTS = {"low": 8, "medium": 4, "high": 0}
IMPORTANT_PAGE_POINTS = 12
PRIORITY_GROUP_POINTS = 6
CONFIDENCE_FACTOR = {"high": 1.0, "medium": 0.85, "low": 0.7}


def prioritise(ctx: AnalysisContext, finding: Finding) -> tuple[float, list[dict[str, Any]]]:
    total_pages = max(1, len(ctx.pages))
    factors: list[dict[str, Any]] = []

    severity = SEVERITY_POINTS[finding.severity.value]
    factors.append(
        {"factor": "severity", "points": severity, "reason": f"{finding.severity.value} severity"}
    )

    affected = total_pages if finding.scope == "site" else finding.affected_page_count
    reach = (
        round(20 * math.log10(1 + affected) / math.log10(1 + total_pages), 1)
        if total_pages > 1
        else 20.0
    )
    factors.append(
        {
            "factor": "reach",
            "points": reach,
            "reason": f"affects {affected} of {total_pages} crawled pages"
            if finding.scope != "site"
            else "affects the whole site",
        }
    )

    important = [u for u in finding.affected_urls if ctx.is_important(u)]
    grouped = [u for u in finding.affected_urls if ctx.priority_group(u)]
    if important or finding.scope == "site":
        factors.append(
            {
                "factor": "page importance",
                "points": IMPORTANT_PAGE_POINTS,
                "reason": "includes the home page or a configured important page"
                if important
                else "site-wide issue",
            }
        )
    elif grouped:
        factors.append(
            {
                "factor": "page importance",
                "points": PRIORITY_GROUP_POINTS,
                "reason": f"in priority page group '{ctx.priority_group(grouped[0])}'",
            }
        )
    else:
        factors.append(
            {"factor": "page importance", "points": 0, "reason": "no important pages affected"}
        )

    effort = EFFORT_POINTS[finding.effort]
    factors.append(
        {"factor": "effort", "points": effort, "reason": f"{finding.effort} effort to fix"}
    )

    subtotal = sum(float(f["points"]) for f in factors)
    confidence = CONFIDENCE_FACTOR[finding.confidence]
    factors.append(
        {
            "factor": "confidence",
            "multiplier": confidence,
            "reason": f"{finding.confidence} confidence in this finding",
        }
    )
    return round(min(100.0, subtotal * confidence), 1), factors
