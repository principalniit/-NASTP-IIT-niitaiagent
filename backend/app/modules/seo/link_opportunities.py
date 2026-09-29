"""Contextual internal-link suggestions.

A suggestion is made only when a source page's own text already mentions the target
page's topic phrase (its H1, or its title without the site-wide branding suffix) and the
source does not yet link to the target. The matched sentence is kept as evidence. Links
are never suggested merely to raise link counts.
"""

import re
import uuid
from dataclasses import dataclass

from app.modules.seo.context import AnalysisContext, PageData
from app.modules.seo.text import common_title_suffix, strip_suffix, tokens

MAX_PER_TARGET = 3
MAX_TOTAL = 500
GENERIC_PHRASES = {"home", "home page", "welcome", "about", "about us", "contact", "contact us",
                   "news", "events", "read more", "click here", "page not found"}  # fmt: skip


@dataclass
class LinkSuggestion:
    source: PageData
    target: PageData
    anchor_text: str
    reason: str
    snippet: str
    relevance: float


def _phrases(page: PageData, suffix: str | None) -> list[str]:
    candidates = [h.get("text", "") for h in page.headings if h.get("level") == 1]
    candidates.append(strip_suffix(page.title, suffix))
    phrases: list[str] = []
    for phrase in candidates:
        phrase = re.sub(r"\s+", " ", phrase or "").strip()
        words = tokens(phrase)
        usable = len(words) >= 2 and len(phrase) >= 8 and phrase.lower() not in GENERIC_PHRASES
        if usable and phrase.lower() not in (p.lower() for p in phrases):
            phrases.append(phrase)
    return phrases


def _snippet(text: str, start: int, end: int) -> str:
    left = max(0, start - 80)
    right = min(len(text), end + 80)
    return ("…" if left else "") + text[left:right].strip() + ("…" if right < len(text) else "")


def suggest_links(ctx: AnalysisContext) -> list[LinkSuggestion]:
    pages = ctx.indexable_pages
    suffix = common_title_suffix(p.title for p in pages)
    minimum = ctx.thresholds.min_inlinks_important
    targets = [
        p for p in pages
        if p.url != ctx.root_url and (
            p.inlinks_count <= 1 or p.is_orphan
            or (ctx.is_important(p.url) and p.inlinks_count < minimum)
        )
    ]  # fmt: skip
    already: dict[uuid.UUID, set[uuid.UUID]] = {}
    for link in ctx.links:
        if link.target_id is not None:
            already.setdefault(link.source_id, set()).add(link.target_id)
    sources = sorted(
        (p for p in pages if p.text),
        key=lambda p: (p.depth if p.depth is not None else 99, -p.inlinks_count, p.url),
    )
    suggestions: list[LinkSuggestion] = []
    for target in targets:
        count = 0
        for phrase in _phrases(target, suffix):
            pattern = re.compile(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", re.IGNORECASE)
            for source in sources:
                if count >= MAX_PER_TARGET or len(suggestions) >= MAX_TOTAL:
                    break
                if source.id == target.id or target.id in already.get(source.id, set()):
                    continue
                match = pattern.search(source.text or "")
                if match is None:
                    continue
                if any(s.source.id == source.id and s.target.id == target.id for s in suggestions):
                    continue
                relevance = round(
                    min(1.0, len(tokens(phrase)) / 6) * 0.8
                    + (0.2 if ctx.is_important(target.url) else 0.0),
                    2,
                )
                suggestions.append(
                    LinkSuggestion(
                        source=source,
                        target=target,
                        anchor_text=match.group(0),
                        reason=(
                            f"This page mentions “{match.group(0)}”, the topic of "
                            f"{target.url}, but does not link to it. The target has "
                            f"{target.inlinks_count} internal link(s)."
                        ),
                        snippet=_snippet(source.text or "", match.start(), match.end()),
                        relevance=relevance,
                    )
                )
                count += 1
    return suggestions
