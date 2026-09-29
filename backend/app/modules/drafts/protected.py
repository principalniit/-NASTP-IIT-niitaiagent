"""Detect drafts that touch official facts: fees, dates, eligibility, deadlines, figures.

Such drafts can only be approved with a verified source reference. Detection is
deliberately broad; a false positive only asks the reviewer for a source.
"""

import re

_FACT_PATTERNS = [
    (r"(?:rs\.?|pkr|usd|\$|€|£)\s?\d[\d,.]*", "an amount of money"),
    (r"\d[\d,.]*\s?(?:%|percent|per cent)", "a percentage"),
    (r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", "a date"),
    (r"\b\d{4}-\d{2}-\d{2}\b", "a date"),
    (
        r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b",
        "a date",
    ),
    (r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2}\b", "a date"),
    (r"\b(?:19|20)\d{2}\b", "a year"),
    (r"\bcgpa\b|\bgpa\b|\bmarks?\b", "grades or marks"),
]
_FACT_KEYWORDS = [
    "fee", "fees", "tuition", "eligibility", "eligible", "deadline", "last date",
    "admission requirement", "admission requirements", "entry requirement", "merit",
    "scholarship amount", "stipend", "refund", "accreditation", "accredited", "ranked",
]  # fmt: skip


def _facts(text: str) -> set[str]:
    found: set[str] = set()
    for pattern, _ in _FACT_PATTERNS:
        found.update(m.group(0).strip().lower() for m in re.finditer(pattern, text, re.I))
    return found


def protected_reasons(original: str | None, proposed: str) -> list[str]:
    """Why a draft needs a verified source before approval (empty if it does not)."""
    reasons: list[str] = []
    before, after = _facts(original or ""), _facts(proposed)
    added = sorted(after - before)
    removed = sorted(before - after)
    if added:
        reasons.append("Introduces factual values: " + ", ".join(added[:10]))
    if removed:
        reasons.append("Removes or changes factual values: " + ", ".join(removed[:10]))
    lowered = proposed.lower()
    keywords = sorted(
        k for k in _FACT_KEYWORDS if re.search(r"(?<!\w)" + re.escape(k) + r"(?!\w)", lowered)
    )
    if keywords:
        reasons.append("Mentions official topics: " + ", ".join(keywords))
    return reasons
