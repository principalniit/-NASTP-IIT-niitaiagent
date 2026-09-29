"""Transparent, configurable site-health scoring.

Each category score is 100 x (1 - penalty), where the penalty is the sum over findings of
severity weight x share of analysed pages affected, capped at 1. Site-wide findings count
as affecting every page. The overall score is the weighted average of the category scores
that could be computed. Scores describe this site's observed health only. They are not a
search engine ranking factor and do not predict rankings.
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from app.modules.seo.context import AnalysisContext
from app.modules.seo.findings import Finding
from app.modules.seo.models import Category


@dataclass
class ScoreResult:
    overall: float | None
    categories: dict[str, float | None]
    pages_analysed: int
    breakdown: dict[str, Any]


def denominators(ctx: AnalysisContext) -> dict[Category, int]:
    html = len(ctx.analysable_pages)
    return {
        Category.TECHNICAL: len(ctx.pages),
        Category.ON_PAGE: html,
        Category.CONTENT: html,
        Category.INTERNAL_LINKING: html,
        Category.STRUCTURED_DATA: html,
    }


def compute_score(ctx: AnalysisContext, findings: list[Finding]) -> ScoreResult:
    severity_weights = ctx.settings.analysis.severity_weights.model_dump()
    category_weights = ctx.settings.analysis.category_weights.model_dump()
    totals = denominators(ctx)
    per_rule: dict[Category, dict[str, dict[str, Any]]] = defaultdict(dict)
    for finding in findings:
        n = totals[finding.category]
        if n == 0:
            continue
        share = 1.0 if finding.scope == "site" else min(1.0, finding.affected_page_count / n)
        penalty = severity_weights[finding.severity.value] * share
        entry = per_rule[finding.category].setdefault(
            finding.rule_id,
            {"rule_id": finding.rule_id, "findings": 0, "affected_pages": 0, "penalty": 0.0},
        )
        entry["findings"] += 1
        entry["affected_pages"] += finding.affected_page_count if finding.scope != "site" else n
        entry["penalty"] += penalty

    categories: dict[str, float | None] = {}
    breakdown: dict[str, Any] = {"method": __doc__.strip() if __doc__ else "", "categories": {}}
    for category in Category:
        n = totals[category]
        rules = sorted(per_rule[category].values(), key=lambda r: -r["penalty"])
        for rule in rules:
            rule["penalty"] = round(min(1.0, rule["penalty"]), 4)
        if n == 0:
            categories[category.value] = None
            breakdown["categories"][category.value] = {
                "score": None,
                "weight": category_weights[category.value],
                "pages_considered": 0,
                "note": "No pages could be analysed for this category.",
                "contributions": [],
            }
            continue
        penalty = min(1.0, sum(r["penalty"] for r in rules))
        score = round(100 * (1 - penalty), 1)
        categories[category.value] = score
        breakdown["categories"][category.value] = {
            "score": score,
            "weight": category_weights[category.value],
            "pages_considered": n,
            "penalty": round(penalty, 4),
            "contributions": rules,
        }

    scored = {k: v for k, v in categories.items() if v is not None and category_weights[k] > 0}
    weight_total = sum(category_weights[k] for k in scored)
    overall = (
        round(sum(v * category_weights[k] for k, v in scored.items()) / weight_total, 1)
        if weight_total
        else None
    )
    breakdown["overall"] = {
        "score": overall,
        "weights_used": {k: category_weights[k] for k in scored},
    }
    breakdown["severity_weights"] = severity_weights
    return ScoreResult(overall, categories, len(ctx.analysable_pages), breakdown)
