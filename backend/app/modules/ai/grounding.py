"""Checks that AI output stays within the evidence it was given.

Hard violations (the output is rejected): numbers that do not appear in the evidence,
references to issues that were not supplied, and claims about rankings, traffic or search
volumes. Soft warnings (shown to reviewers): length limits and terminology to avoid.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
_NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*(?![\w])")
# "1. ", "2) " at the start of a line: list numbering, not a fact to check.
_LIST_MARKER = re.compile(r"(?m)^\s*\d{1,2}[.)]\s+")
_CLAIMS = [
    (r"\bguarantee", "promises a guaranteed outcome"),
    (r"\b(?:rank|ranking|position)\s*(?:#|no\.?|number)?\s*\d[\d.,]*", "states a ranking position"),
    (
        r"\b(?:first|top)\s+(?:page|result|spot|position)s?\s+(?:of|on|in)\s+"
        r"(?:google|bing|search)",
        "promises a search position",
    ),
    (r"\b(?:search|keyword)\s+volumes?\s+(?:of|is|are|was)\b", "states a search volume"),
    (
        r"\b\d[\d,.]*\s*%?\s+(?:more\s+)?"
        r"(?:visits|visitors|searches|clicks|impressions|backlinks)\b",
        "states traffic or backlink figures",
    ),
    (r"\btraffic\s+(?:will|would|should)\s+(?:increase|grow|double|rise)", "predicts traffic"),
]
FORBIDDEN_CLAIMS = [(re.compile(pattern, re.I), description) for pattern, description in _CLAIMS]
# Claims that may report imported Search Console figures, for example "80 clicks" or
# "average position 3.5": allowed only when the evidence holds search data, every number
# in the claim comes from it, and the sentence reports rather than predicts.
_GROUNDED_NUMBERS_OK = frozenset(
    {"states a ranking position", "states traffic or backlink figures"}
)
_PREDICTIVE = re.compile(
    r"\b(will|would|could|can|might|expect\w*|reach\w*|gain\w*|more|increase\w*|boost\w*|"
    r"grow\w*|achiev\w*|improv\w*|get you)\b",
    re.I,
)


def _has_key(value: Any, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_has_key(v, key) for v in value.values())
    if isinstance(value, list):
        return any(_has_key(v, key) for v in value)
    return False


def _sentence(text: str, start: int, end: int) -> str:
    begin = max(text.rfind(". ", 0, start), text.rfind("\n", 0, start)) + 1
    stop = min(
        (i for i in (text.find(". ", end), text.find("\n", end)) if i != -1), default=len(text)
    )
    return text[begin:stop]


def _reports_search_data(match: re.Match[str], text: str, allowed: set[str], evidence: Any) -> bool:
    return (
        _has_key(evidence, "search_performance")
        and numbers_in(match.group(0)) <= allowed
        and not _PREDICTIVE.search(_sentence(text, match.start(), match.end()))
    )


@dataclass
class GroundingReport:
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # The specifics behind the violations, for the retry instruction.
    numbers: list[str] = field(default_factory=list)
    unknown_issues: list[str] = field(default_factory=list)
    claims: list[str] = field(default_factory=list)

    def retry_instruction(self) -> str:
        """What to change, specifically enough for a small model to act on."""
        parts = []
        if self.numbers:
            parts.append(
                "Remove these numbers, or replace them with the exact figures from the evidence: "
                + ", ".join(self.numbers)
                + ". Do not count, add, subtract or calculate anything yourself; only copy "
                "numbers exactly as they appear in the evidence, or describe without numbers."
            )
        if self.unknown_issues:
            parts.append(
                "Cite only issue references that appear in the evidence (such as issue-a). "
                "These were not in it: " + ", ".join(self.unknown_issues) + "."
            )
        for claim in self.claims:
            parts.append(
                f"Remove the statement that {claim}: the platform has no data for it. You may "
                "say that this data is not available."
            )
        return "Your reply was rejected because it is not grounded in the evidence. " + " ".join(
            parts
        )

    @property
    def passed(self) -> bool:
        return not self.violations

    def as_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "violations": self.violations, "warnings": self.warnings}


def _normalise(number: str) -> str:
    value = number.replace(",", "")
    if "." in value:
        value = value.rstrip("0").rstrip(".") or "0"
    return value


def numbers_in(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, bool):
        return found
    if isinstance(value, (int, float)):
        found.add(_normalise(repr(value)))
    elif isinstance(value, str):
        text = _LIST_MARKER.sub(" ", _UUID.sub(" ", value))
        found.update(_normalise(n) for n in _NUMBER.findall(text))
    elif isinstance(value, dict):
        for item in value.values():
            found |= numbers_in(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            found |= numbers_in(item)
    return found


def _texts(value: Any, skip: set[str]) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [t for k, v in value.items() if k not in skip for t in _texts(v, skip)]
    if isinstance(value, list):
        return [t for item in value for t in _texts(item, skip)]
    return []


def _ids(value: Any) -> set[str]:
    if isinstance(value, dict):
        found: set[str] = set()
        for key, item in value.items():
            if key == "issue_ids" and isinstance(item, list):
                found.update(str(i) for i in item)
            else:
                found |= _ids(item)
        return found
    if isinstance(value, list):
        return {i for item in value for i in _ids(item)}
    return set()


def check_output(
    output: BaseModel, evidence: dict[str, Any], known_issue_ids: set[str]
) -> GroundingReport:
    report = GroundingReport()
    data = output.model_dump(mode="json")
    texts = _texts(data, skip={"issue_ids"})
    allowed = numbers_in(evidence)
    unsupported = sorted({n for t in texts for n in numbers_in(t)} - allowed, key=len)
    if unsupported:
        report.numbers = unsupported[:10]
        report.violations.append(
            "Uses numbers that are not in the project data: " + ", ".join(report.numbers)
        )
    unknown = sorted(_ids(data) - known_issue_ids)
    if unknown:
        report.unknown_issues = unknown[:5]
        report.violations.append(
            "Refers to issues that were not provided: " + ", ".join(report.unknown_issues)
        )
    for text in texts:
        for pattern, description in FORBIDDEN_CLAIMS:
            match = pattern.search(text)
            if (
                match
                and description in _GROUNDED_NUMBERS_OK
                and _reports_search_data(match, text, allowed, evidence)
            ):
                continue
            if match and description not in report.claims:
                report.claims.append(description)
                report.violations.append(f"Makes an unsupported claim: {description}")
    return report


def terminology_warnings(texts: list[str], terminology: list[dict[str, Any]]) -> list[str]:
    warnings = []
    joined = " ".join(texts).lower()
    for entry in terminology:
        for avoid in entry.get("avoid", []):
            if avoid and re.search(r"(?<!\w)" + re.escape(avoid.lower()) + r"(?!\w)", joined):
                warnings.append(f"Uses '{avoid}'; the approved term is '{entry.get('preferred')}'")
    return warnings
