import gzip

import pytest

from app.modules.crawler.sitemaps import SitemapError, parse_sitemap

URLSET = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc> https://example.org/ </loc></url>
  <url><loc>https://example.org/about</loc><lastmod>2026-01-01</lastmod></url>
</urlset>"""

INDEX = b"""<?xml version="1.0"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.org/s1.xml</loc></sitemap>
</sitemapindex>"""


def test_urlset_and_index() -> None:
    content = parse_sitemap(URLSET)
    assert content.kind == "urlset"
    assert content.urls == ["https://example.org/", "https://example.org/about"]
    index = parse_sitemap(INDEX)
    assert index.kind == "index"
    assert index.sitemaps == ["https://example.org/s1.xml"]


def test_gzip_sitemap() -> None:
    assert parse_sitemap(gzip.compress(URLSET)).urls[1] == "https://example.org/about"


def test_rejects_invalid_documents() -> None:
    with pytest.raises(SitemapError):
        parse_sitemap(b"<html><body>not a sitemap</body></html>")
    with pytest.raises(SitemapError):
        parse_sitemap(b"<urlset><url><loc>broken")
    with pytest.raises(SitemapError):
        parse_sitemap(b"\x1f\x8bnot really gzip")


def test_external_entities_are_not_resolved() -> None:
    xxe = b"""<?xml version="1.0"?>
<!DOCTYPE urlset [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>&xxe;</loc></url></urlset>"""
    try:
        content = parse_sitemap(xxe)
    except SitemapError:
        return
    assert all("root:" not in url for url in content.urls)


def test_entity_expansion_bomb_is_harmless() -> None:
    bomb = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
<!ENTITY lol4 "&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;">
<!ENTITY lol5 "&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;">
<!ENTITY lol6 "&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;">]>
<urlset><url><loc>&lol6;</loc></url></urlset>"""
    try:
        content = parse_sitemap(bomb)
    except SitemapError:
        return
    assert all(len(url) < 1000 for url in content.urls)


def test_gzip_bomb_is_rejected() -> None:
    bomb = gzip.compress(b"<urlset>" + b" " * (51 * 1024 * 1024) + b"</urlset>")
    with pytest.raises(SitemapError):
        parse_sitemap(bomb)
