from app.modules.crawler.robots import RobotsPolicy, RobotsTxt, product_token

UA = "NIIT-SEO-Agent/0.1 (+https://niit.edu.pk)"

ROBOTS = """
# comment
User-agent: *
Disallow: /private/
Allow: /private/public-page
Disallow: /*.pdf$
Disallow: /search?
Crawl-delay: 2

User-agent: BadBot
Disallow: /

Sitemap: https://example.org/sitemap.xml
"""


def test_product_token() -> None:
    assert product_token(UA) == "niit-seo-agent"


def test_wildcard_group_rules() -> None:
    robots = RobotsTxt.parse(ROBOTS)
    assert robots.can_fetch(UA, "/")
    assert not robots.can_fetch(UA, "/private/secret")
    assert robots.can_fetch(UA, "/private/public-page")  # longer Allow wins
    assert not robots.can_fetch(UA, "/files/report.pdf")
    assert robots.can_fetch(UA, "/files/report.pdf?download=1")  # $ anchors the end
    assert not robots.can_fetch(UA, "/search?q=x")
    assert robots.can_fetch(UA, "/searching")
    assert robots.can_fetch(UA, "/robots.txt")
    assert robots.crawl_delay(UA) == 2.0
    assert robots.sitemaps == ["https://example.org/sitemap.xml"]
    assert not robots.can_fetch("BadBot/1.0", "/anything")


def test_specific_group_overrides_wildcard_and_merges() -> None:
    robots = RobotsTxt.parse(
        "User-agent: *\nDisallow: /\n\n"
        "User-agent: niit-seo-agent\nDisallow: /a\n\n"
        "User-agent: NIIT-SEO-Agent\nDisallow: /b\n"
    )
    assert robots.can_fetch(UA, "/c")
    assert not robots.can_fetch(UA, "/a")
    assert not robots.can_fetch(UA, "/b")


def test_equal_length_tie_prefers_allow_and_empty_disallow_allows_all() -> None:
    robots = RobotsTxt.parse("User-agent: *\nDisallow: /page\nAllow: /page\n")
    assert robots.can_fetch(UA, "/page")
    assert RobotsTxt.parse("User-agent: *\nDisallow:\n").can_fetch(UA, "/x")


def test_multiple_agents_share_a_group() -> None:
    robots = RobotsTxt.parse("User-agent: a\nUser-agent: niit-seo-agent\nDisallow: /x\n")
    assert not robots.can_fetch(UA, "/x")


def test_crawl_delay_is_capped() -> None:
    assert RobotsTxt.parse("User-agent: *\nCrawl-delay: 9999\n").crawl_delay(UA) == 30.0


def test_policy_statuses() -> None:
    assert RobotsPolicy("not_found").can_fetch(UA, "/anything")
    unreachable = RobotsPolicy("unreachable")
    assert not unreachable.can_fetch(UA, "/")
    assert unreachable.can_fetch(UA, "/robots.txt")
