"""Minimal, conservative checks of JSON-LD against common schema.org types.

This is not a full schema.org validator. It checks a small set of properties that search
engines document as required or recommended for common types, and reports everything
else as unchecked rather than guessing.
"""

from dataclasses import dataclass, field
from typing import Any

ORGANISATION_TYPES = {
    "Organization", "EducationalOrganization", "CollegeOrUniversity", "School", "HighSchool",
    "MiddleSchool", "ElementarySchool", "Preschool", "Corporation", "NGO",
    "GovernmentOrganization", "LocalBusiness",
}  # fmt: skip

# Maps each schema.org type to (required properties, recommended properties).
REQUIREMENTS: dict[str, tuple[list[str], list[str]]] = {
    **{
        t: (["name"], ["url", "logo", "address", "contactPoint", "sameAs"])
        for t in ORGANISATION_TYPES
    },
    "WebSite": (["name", "url"], []),
    "BreadcrumbList": (["itemListElement"], []),
    "Course": (["name", "description"], ["provider"]),
    "Event": (
        ["name", "startDate", "location"],
        ["endDate", "description", "eventStatus", "image", "organizer"],
    ),
    "FAQPage": (["mainEntity"], []),
    "Article": (["headline"], ["datePublished", "author", "image"]),
    "NewsArticle": (["headline"], ["datePublished", "author", "image"]),
    "BlogPosting": (["headline"], ["datePublished", "author", "image"]),
    "Person": (["name"], ["jobTitle", "affiliation"]),
}


@dataclass
class BlockCheck:
    format: str
    types: list[str]
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _present(value: Any) -> bool:
    return value not in (None, "", [], {})


def _nodes(data: Any) -> list[dict[str, Any]]:
    """Every object carrying an @type, including inside @graph and nested values."""
    found: list[dict[str, Any]] = []
    if isinstance(data, dict):
        if "@type" in data:
            found.append(data)
        for value in data.values():
            if isinstance(value, (dict, list)):
                found.extend(_nodes(value))
    elif isinstance(data, list):
        for item in data:
            found.extend(_nodes(item))
    return found


def _types(node: dict[str, Any]) -> list[str]:
    value = node.get("@type")
    values = value if isinstance(value, list) else [value]
    return [v.rsplit("/", 1)[-1] for v in values if isinstance(v, str)]


def check_page(structured_data: dict[str, Any]) -> list[BlockCheck]:
    results: list[BlockCheck] = []
    for block in structured_data.get("json_ld", []) or []:
        if not block.get("valid"):
            results.append(
                BlockCheck("json_ld", [], False, errors=[block.get("error") or "Invalid JSON"])
            )
            continue
        data = block.get("data")
        check = BlockCheck("json_ld", list(block.get("types") or []), True)
        if data is None:
            check.warnings.append(block.get("error") or "Block too large to check properties")
            results.append(check)
            continue
        nodes = _nodes(data)
        if not nodes:
            check.valid = False
            check.errors.append("No @type found, so search engines cannot interpret this block")
        for node in nodes:
            for type_name in _types(node):
                rules = REQUIREMENTS.get(type_name)
                if rules is None:
                    continue
                required, recommended = rules
                for prop in required:
                    if not _present(node.get(prop)):
                        check.valid = False
                        check.errors.append(f"{type_name} is missing required property '{prop}'")
                for prop in recommended:
                    if not _present(node.get(prop)):
                        check.warnings.append(
                            f"{type_name} could add recommended property '{prop}'"
                        )
        results.append(check)
    microdata = structured_data.get("microdata") or {}
    if microdata.get("count"):
        results.append(
            BlockCheck(
                "microdata",
                [t.rsplit("/", 1)[-1] for t in microdata.get("types", [])],
                True,
                warnings=["Microdata properties are detected but not checked"],
            )
        )
    return results


def page_types(structured_data: dict[str, Any]) -> set[str]:
    return {t for check in check_page(structured_data) for t in check.types}
