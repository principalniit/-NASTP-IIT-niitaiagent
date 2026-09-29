"""Rule registry. Every rule is deterministic and runs without AI."""

from app.modules.seo.rules import content, linking, on_page, structured_data, technical
from app.modules.seo.rules.base import Rule

ALL_RULES: list[Rule] = [
    *technical.RULES,
    *on_page.RULES,
    *content.RULES,
    *linking.RULES,
    *structured_data.RULES,
]

_ids = [rule.id for rule in ALL_RULES]
assert len(_ids) == len(set(_ids)), "Rule identifiers must be unique"  # noqa: S101


def rule_catalogue() -> list[dict[str, object]]:
    return [rule.catalogue_entry() for rule in ALL_RULES]
