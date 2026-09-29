from pathlib import Path

from app.modules.crawler.parser import parse_html, robots_directives

FIXTURE = (Path(__file__).parent.parent / "fixtures" / "page_full.html").read_bytes()
URL = "https://example.org/admissions/"


def test_extracts_metadata() -> None:
    page = parse_html(FIXTURE, URL)
    assert page.title == "Admissions 2026 | Example Institute"
    assert page.title_count == 1
    assert page.meta_description == "How to apply."
    assert page.meta_robots == "index, follow"
    assert page.canonical_url == "https://example.org/admissions/"
    assert page.canonical_count == 1
    assert page.lang == "en-PK"
    assert page.hreflang == [{"hreflang": "ur", "href": "https://example.org/ur/admissions/"}]


def test_extracts_headings_images_and_words() -> None:
    page = parse_html(FIXTURE, URL)
    assert [(h["level"], h["text"]) for h in page.headings] == [
        (1, "Admissions"),
        (2, "How to apply"),
        (3, "Deadlines"),
    ]
    assert page.h1_count == 1
    assert page.image_count == 4
    assert page.images_missing_alt == 1
    assert page.images[0] == {
        "src": "https://example.org/admissions/banner.jpg",
        "alt": "Campus entrance",
        "has_alt": True,
    }
    assert page.images[1]["alt"] == "" and page.images[1]["has_alt"]
    # Script and style text is excluded from the word count.
    assert "hidden" not in str(page.word_count)
    assert 15 <= page.word_count <= 40
    assert page.content_hash and len(page.content_hash) == 64


def test_extracts_links_with_base_and_rel() -> None:
    page = parse_html(FIXTURE, URL)
    links = {(link.url, link.nofollow): link.anchor_text for link in page.links}
    assert links[("https://example.org/admissions/apply", False)] == "Apply now"
    assert ("https://example.org/contact", True) in links
    assert ("https://example.org/contact", False) in links
    assert ("https://external.example.com/page", False) in links
    assert links[("https://example.org/programmes", False)] == "Programmes"
    assert ("https://example.org/admissions/", False) in links  # the #top fragment
    assert all(not url.startswith("mailto") for url, _ in links)


def test_structured_data() -> None:
    data = parse_html(FIXTURE, URL).structured_data
    valid, invalid = data["json_ld"]
    assert valid["valid"] and valid["types"] == ["CollegeOrUniversity", "FAQPage", "WebPage"]
    assert not invalid["valid"] and invalid["error"].startswith("Invalid JSON")
    assert data["microdata"] == {"count": 1, "types": ["https://schema.org/Event"]}


def test_content_hash_ignores_whitespace_and_case() -> None:
    a = parse_html(b"<html><body><p>Hello   World</p></body></html>", URL)
    b = parse_html(b"<html><body><div>hello\nworld</div></body></html>", URL)
    c = parse_html(b"<html><body><p>Hello there</p></body></html>", URL)
    assert a.content_hash == b.content_hash != c.content_hash


def test_handles_empty_and_broken_markup() -> None:
    page = parse_html(b"", URL)
    assert page.title is None and page.word_count == 0 and page.content_hash is None
    broken = parse_html(b"<html><title>A</title><title>B</title><h1>x<h1>y", URL)
    assert broken.title_count == 2
    assert broken.h1_count == 2


def test_robots_directives() -> None:
    assert robots_directives("NOINDEX, follow") == {"noindex", "follow"}
    assert robots_directives("googlebot: noindex") == {"noindex"}
    assert robots_directives(None) == set()
