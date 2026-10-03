"""Extract SEO-relevant facts from an HTML document.

Everything here is observation, not judgement: the rules engine (Phase 3) decides what
counts as an issue.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

from selectolax.lexbor import LexborHTMLParser, LexborNode

from app.modules.crawler.urls import normalise_url

MAX_TEXT = 500
MAX_ANCHOR = 300
MAX_IMAGES = 500
MAX_LINKS = 2000
MAX_JSON_LD_BYTES = 50_000
MAX_TEXT_CHARS = 50_000
NON_CONTENT_TAGS = ["script", "style", "noscript", "template", "svg", "iframe"]
_WS = re.compile(r"\s+")
_WORD = re.compile(r"\w+", re.UNICODE)
# Links such as href="#/about" or "#!/about": pages of a single-page site that exist only
# after the #, which search engines treat as one address.
_HASH_ROUTE = re.compile(r"""href\s*=\s*["']#!?/[^"'\s]""", re.IGNORECASE)


def hash_route_links(html: bytes | str) -> int:
    """How many links point to #/ or #!/ addresses."""
    text = html.decode("utf-8", errors="replace") if isinstance(html, bytes) else html
    return len(_HASH_ROUTE.findall(text))


def _clean(text: str | None, limit: int = MAX_TEXT) -> str:
    return _WS.sub(" ", text or "").strip()[:limit]


@dataclass
class ExtractedLink:
    url: str
    anchor_text: str
    nofollow: bool


@dataclass
class ParsedPage:
    title: str | None = None
    title_count: int = 0
    meta_description: str | None = None
    meta_description_count: int = 0
    meta_robots: str | None = None
    canonical_url: str | None = None
    canonical_count: int = 0
    lang: str | None = None
    headings: list[dict[str, Any]] = field(default_factory=list)
    h1_count: int = 0
    word_count: int = 0
    content_hash: str | None = None
    text: str = ""
    images: list[dict[str, Any]] = field(default_factory=list)
    image_count: int = 0
    images_missing_alt: int = 0
    links: list[ExtractedLink] = field(default_factory=list)
    structured_data: dict[str, Any] = field(default_factory=dict)
    hreflang: list[dict[str, str]] = field(default_factory=list)


def robots_directives(value: str | None) -> set[str]:
    """Directive names from a meta robots or X-Robots-Tag value.

    Handles bot-prefixed header values such as 'googlebot: noindex'.
    """
    directives: set[str] = set()
    for part in (value or "").lower().split(","):
        token = part.strip()
        if ":" in token:
            token = token.split(":", 1)[1].strip()
        if token:
            directives.add(token)
    return directives


def _json_ld_types(node: Any) -> list[str]:
    types: list[str] = []
    if isinstance(node, dict):
        value = node.get("@type")
        if isinstance(value, str):
            types.append(value)
        elif isinstance(value, list):
            types.extend(v for v in value if isinstance(v, str))
        for child in node.values():
            if isinstance(child, (dict, list)):
                types.extend(_json_ld_types(child))
    elif isinstance(node, list):
        for item in node:
            types.extend(_json_ld_types(item))
    return types


def _structured_data(tree: LexborHTMLParser) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    for script in tree.css("script"):
        script_type = (script.attributes.get("type") or "").split(";", 1)[0].strip().lower()
        if script_type != "application/ld+json":
            continue
        raw = script.text(deep=True) or ""
        block: dict[str, Any] = {"valid": True, "error": None, "types": [], "data": None}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            block.update(valid=False, error=f"Invalid JSON at line {exc.lineno}: {exc.msg}")
        else:
            block["types"] = sorted(set(_json_ld_types(data)))
            if len(raw) <= MAX_JSON_LD_BYTES:
                block["data"] = data
            else:
                block["error"] = "Block larger than 50 KB; content not stored"
        blocks.append(block)
    microdata_types = sorted(
        {
            itemtype
            for node in tree.css("[itemscope]")
            for itemtype in (node.attributes.get("itemtype") or "").split()
        }
    )
    return {
        "json_ld": blocks,
        "microdata": {"count": len(tree.css("[itemscope]")), "types": microdata_types},
    }


def _anchor_text(node: LexborNode) -> str:
    text = _clean(node.text(deep=True), MAX_ANCHOR)
    if text:
        return text
    image = node.css_first("img[alt]")
    return _clean(image.attributes.get("alt") if image else None, MAX_ANCHOR)


def parse_html(html: bytes | str, page_url: str) -> ParsedPage:
    tree = LexborHTMLParser(html)
    page = ParsedPage()

    base_url = page_url
    base = tree.css_first("base[href]")
    if base is not None:
        resolved = normalise_url(base.attributes.get("href") or "", page_url)
        if resolved:
            base_url = resolved

    titles = tree.css("head > title")
    page.title_count = len(titles)
    if titles:
        page.title = _clean(titles[0].text(deep=True), 1000)

    descriptions: list[str] = []
    robots_values: list[str] = []
    for meta in tree.css("meta[name]"):
        name = (meta.attributes.get("name") or "").strip().lower()
        content = meta.attributes.get("content") or ""
        if name == "description":
            descriptions.append(_clean(content, 2000))
        elif name == "robots":
            robots_values.append(_clean(content, 300))
    page.meta_description_count = len(descriptions)
    page.meta_description = descriptions[0] if descriptions else None
    page.meta_robots = ", ".join(robots_values) or None

    canonicals: list[str] = []
    for link in tree.css("link[rel][href]"):
        rels = (link.attributes.get("rel") or "").lower().split()
        href = link.attributes.get("href") or ""
        if "canonical" in rels:
            canonicals.append(normalise_url(href, base_url) or href.strip())
        elif "alternate" in rels and link.attributes.get("hreflang"):
            page.hreflang.append(
                {
                    "hreflang": _clean(link.attributes.get("hreflang"), 35),
                    "href": normalise_url(href, base_url) or href.strip(),
                }
            )
    page.canonical_count = len(canonicals)
    page.canonical_url = canonicals[0][:2048] if canonicals else None

    html_node = tree.css_first("html")
    if html_node is not None and html_node.attributes.get("lang"):
        page.lang = _clean(html_node.attributes.get("lang"), 35)

    for heading in tree.css("h1, h2, h3, h4, h5, h6"):
        level = int((heading.tag or "h0")[1])
        page.headings.append({"level": level, "text": _clean(heading.text(deep=True))})
    page.h1_count = sum(1 for h in page.headings if h["level"] == 1)

    images = tree.css("img")
    page.image_count = len(images)
    for image in images:
        has_alt = "alt" in image.attributes
        if not has_alt:
            page.images_missing_alt += 1
        if len(page.images) < MAX_IMAGES:
            src = image.attributes.get("src") or ""
            page.images.append(
                {
                    "src": (normalise_url(src, base_url) or src.strip())[:2048],
                    "alt": _clean(image.attributes.get("alt")) if has_alt else None,
                    "has_alt": has_alt,
                }
            )

    seen: set[tuple[str, bool]] = set()
    for anchor in tree.css("a[href]"):
        url = normalise_url(anchor.attributes.get("href") or "", base_url)
        if url is None:
            continue
        nofollow = "nofollow" in (anchor.attributes.get("rel") or "").lower().split()
        key = (url, nofollow)
        if key in seen:
            continue
        seen.add(key)
        page.links.append(ExtractedLink(url, _anchor_text(anchor), nofollow))
        if len(page.links) >= MAX_LINKS:
            break

    page.structured_data = _structured_data(tree)

    body = tree.body
    if body is not None:
        body.strip_tags(NON_CONTENT_TAGS)
        text = _WS.sub(" ", body.text(separator=" ")).strip()
        page.word_count = len(_WORD.findall(text))
        page.text = text[:MAX_TEXT_CHARS]
        if text:
            page.content_hash = hashlib.sha256(text.lower().encode()).hexdigest()
    return page
