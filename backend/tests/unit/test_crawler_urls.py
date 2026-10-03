import pytest

from app.modules.crawler.urls import is_excluded, normalise_url, path_with_query, www_twin


@pytest.mark.parametrize(
    ("raw", "base", "expected"),
    [
        ("HTTPS://Example.ORG:443/a/../b/./c?x=1#frag", None, "https://example.org/b/c?x=1"),
        ("/about", "https://example.org/x/y", "https://example.org/about"),
        ("page", "https://example.org/x/y", "https://example.org/x/page"),
        ("//cdn.example.org/i.png", "https://example.org/", "https://cdn.example.org/i.png"),
        ("http://example.org:8080", None, "http://example.org:8080/"),
        ("?q=2", "https://example.org/s?q=1", "https://example.org/s?q=2"),
    ],
)
def test_normalise_url(raw: str, base: str | None, expected: str) -> None:
    assert normalise_url(raw, base) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "mailto:a@b.org",
        "javascript:void(0)",
        "tel:+92",
        "data:text/html,x",
        "ftp://x.org/",
        "https://user:pw@example.org/",
        "https://example.org:99999/",
        "",
        "   ",
        "https://",
    ],
)
def test_normalise_url_rejects_uncrawlable(raw: str) -> None:
    assert normalise_url(raw, "https://example.org/") is None


def test_fragment_only_link_resolves_to_same_page() -> None:
    assert normalise_url("#top", "https://example.org/a") == "https://example.org/a"


def test_exclusions_and_paths() -> None:
    assert is_excluded("https://example.org/wp-admin/x", ["/wp-admin/*"])
    assert not is_excluded("https://example.org/news", ["/wp-admin/*"])
    assert path_with_query("https://example.org/a?b=1") == "/a?b=1"
    assert path_with_query("https://example.org") == "/"


def test_the_www_and_bare_names_are_one_site() -> None:
    assert www_twin("example.org") == "www.example.org"
    assert www_twin("www.example.org") == "example.org"
    assert www_twin("admissions.example.org") == "www.admissions.example.org"
    for no_domain in ("localhost", "127.0.0.1", "::1"):
        assert www_twin(no_domain) is None
