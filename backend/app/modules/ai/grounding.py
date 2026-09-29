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
_CLAIMS = [
    (r"\bguarantee", "promises a guaranteed outcome"),
    (r"\b(?:rank|ranking|position)\s*(?:#|no\.?|number)?\s*\d", "states a ranking position"),
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


@dataclass
class GroundingReport:
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

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
        found.update(_normalise(n) for n in _NUMBER.findall(_UUID.sub(" ", value)))
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
        report.violations.append(
            "Uses numbers that are not in the project data: " + ", ".join(unsupported[:10])
        )
    unknown = sorted(_ids(data) - known_issue_ids)
    if unknown:
        report.violations.append(
            "Refers to issues that were not provided: " + ", ".join(unknown[:5])
        )
    for text in texts:
        for pattern, description in FORBIDDEN_CLAIMS:
            if pattern.search(text):
                report.violations.append(f"Makes an unsupported claim: {description}")
    report.violations = list(dict.fromkeys(report.violations))
    return report


def terminology_warnings(texts: list[str], terminology: list[dict[str, Any]]) -> list[str]:
    warnings = []
    joined = " ".join(texts).lower()
    for entry in terminology:
        for avoid in entry.get("avoid", []):
            if avoid and re.search(r"(?<!\w)" + re.escape(avoid.lower()) + r"(?!\w)", joined):
                warnings.append(f"Uses '{avoid}'; the approved term is '{entry.get('preferred')}'")
    return warnings
