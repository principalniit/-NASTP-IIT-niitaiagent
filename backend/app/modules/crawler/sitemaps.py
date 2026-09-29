"""XML sitemap parsing, hardened against oversized and malicious input."""

import zlib
from dataclasses import dataclass, field

from lxml import etree

MAX_SITEMAP_BYTES = 50 * 1024 * 1024  # protocol limit for an uncompressed sitemap
MAX_URLS_PER_SITEMAP = 50_000


class SitemapError(ValueError):
    pass


@dataclass
class SitemapContent:
    kind: str  # "urlset" or "index"
    urls: list[str] = field(default_factory=list)
    sitemaps: list[str] = field(default_factory=list)


def _gunzip(data: bytes) -> bytes:
    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    out = decompressor.decompress(data, MAX_SITEMAP_BYTES + 1)
    if len(out) > MAX_SITEMAP_BYTES or decompressor.unconsumed_tail:
        raise SitemapError("Sitemap is larger than 50 MB when decompressed")
    return out


def _local(tag: object) -> str:
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def parse_sitemap(data: bytes) -> SitemapContent:
    if data[:2] == b"\x1f\x8b":
        try:
            data = _gunzip(data)
        except zlib.error as exc:
            raise SitemapError("Sitemap could not be decompressed") from exc
    if len(data) > MAX_SITEMAP_BYTES:
        raise SitemapError("Sitemap is larger than 50 MB")
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        huge_tree=False,
        recover=False,
    )
    try:
        root = etree.fromstring(data, parser)
    except etree.XMLSyntaxError as exc:
        raise SitemapError(f"Sitemap is not valid XML: {exc.msg}") from exc
    kind = _local(root.tag)
    if kind not in ("urlset", "sitemapindex"):
        raise SitemapError("Document is not a sitemap (expected urlset or sitemapindex)")
    locs: list[str] = []
    for element in root.iter():
        if _local(element.tag) == "loc" and element.text and element.text.strip():
            locs.append(element.text.strip())
            if len(locs) >= MAX_URLS_PER_SITEMAP:
                break
    if kind == "urlset":
        return SitemapContent("urlset", urls=locs)
    return SitemapContent("index", sitemaps=locs)
