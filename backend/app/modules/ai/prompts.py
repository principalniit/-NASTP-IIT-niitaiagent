"""Prompts. The version is stored with every analysis so outputs can be traced."""

import json
from typing import Any

from pydantic import BaseModel

from app.modules.organisations.schemas import OrganisationSettings

PROMPT_VERSION = "2026-10.7"

RULES = """Rules you must follow:
1. Use only facts contained in EVIDENCE. If the answer is not in the evidence, say that the
   information is not available in the project data.
2. Never invent, estimate or guess numbers. This platform has no data on visitor numbers,
   keyword search volumes, backlinks or competitors: do not mention them. Google Search
   clicks, impressions and positions are known only when EVIDENCE contains
   search_performance from Google Search Console. Then quote its figures exactly, as Google
   Search figures for its period, never as all visitors and never as a forecast. Without it,
   do not mention rankings or traffic.
3. Never promise search results or ranking outcomes. Describe benefits in general terms.
4. Keep observations (what the evidence shows) separate from recommendations (what to do).
5. Do not state or change official facts such as dates, fees, eligibility, admission
   requirements or institutional claims. Where content needs such a fact, write
   [verify: <what is needed>] instead.
6. Issues in the evidence have short references such as issue-a. Put the references of the
   issues you rely on in the issue_ids fields, copied exactly; in sentences, name issues by
   their title. Never cite an issue that is not in the evidence.
7. Reply with JSON only, matching the requested schema."""


def system_prompt(org_name: str, settings: OrganisationSettings, language: str) -> str:
    parts = [
        f"You are an SEO assistant helping the web team of {org_name}.",
        f"Write in the language with code '{language}'.",
    ]
    if settings.brand_tone:
        parts.append(f"Brand tone: {settings.brand_tone}")
    if settings.approved_terminology:
        terms = "; ".join(
            f"use '{t.preferred}'"
            + (f" instead of {', '.join(repr(a) for a in t.avoid)}" if t.avoid else "")
            for t in settings.approved_terminology[:30]
        )
        parts.append(f"Approved terminology: {terms}.")
    parts.append(RULES)
    return "\n".join(parts)


def user_prompt(task: str, evidence: dict[str, Any], schema: type[BaseModel]) -> str:
    data = json.dumps(evidence, ensure_ascii=False, default=str)
    return (
        f"TASK:\n{task}\n\nEVIDENCE (JSON):\n{data}\n\n"
        f"Reply with JSON matching this schema:\n{json.dumps(schema.model_json_schema())}"
    )
