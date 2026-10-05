"""Working out what a question is about, so the matching data is fetched first."""

from app.modules.ai.topics import (
    admit_missing,
    is_priority_question,
    page_in,
    topics_in,
    unavailable_in,
)


def labels(question: str) -> list[str]:
    return [t.label for t in topics_in(question)]


def test_topics_are_found_from_the_wording() -> None:
    assert labels("Are there any broken links or pages that return errors?") == [
        "broken links and error pages"
    ]
    assert labels("Which pages have problems with their titles or meta descriptions?") == [
        "titles",
        "meta descriptions",
    ]
    assert labels("Which pages are missing an H1 heading?") == ["headings"]
    assert labels("Do any images lack alt text?") == ["images and alt text"]
    assert labels("Is our structured data valid?") == ["structured data"]
    assert labels("Why is the site slow?") == ["page speed"]
    assert labels("How healthy is the website overall?") == []


def test_priority_questions() -> None:
    for question in ("What should we fix first?", "So what should be the way forward now?"):
        assert is_priority_question(question), question
    assert not is_priority_question("How many visitors did we get last month?")


def test_pages_named_in_a_question() -> None:
    assert page_in("What is wrong with /admissions/fee-structure?") == "/admissions/fee-structure"
    assert page_in("Check https://niit.edu.pk/about.") == "https://niit.edu.pk/about"
    assert page_in("What should we fix first?") is None
    assert page_in("Is the score 74.3/100 good?") is None


def test_questions_about_data_the_platform_lacks() -> None:
    assert unavailable_in("Which competitors rank above us on Google?") == [
        "search rankings and positions",
        "competitors",
    ]
    assert unavailable_in("How many visitors did the website get last month?") == [
        "visitor numbers and traffic"
    ]
    assert unavailable_in("Which pages are missing an H1 heading?") == []
    # Comparing with other institutions needs data on them, which no source here has.
    assert unavailable_in(
        "How do we rank against other universities for BS Computer Science in Lahore?"
    ) == ["search rankings and positions", "competitors"]
    assert unavailable_in("Is our site faster than other websites?") == ["competitors"]
    assert unavailable_in("Which pages compete for the same keyword?") == [
        "keywords and search volumes"
    ]
    assert unavailable_in("How many conversions did the admissions page get?") == [
        "conversions and bounce rate"
    ]
    assert unavailable_in("Which pages have a low click-through rate?") == [
        "Google Search clicks and impressions"
    ]


def test_answers_open_with_the_data_the_platform_lacks() -> None:
    found = {"not_available": {"data": ["competitors"], "note": "..."}}
    drifted = "Several pages are missing an H1 heading."
    assert admit_missing(drifted, found) == (
        "This platform has no data on competitors. Several pages are missing an H1 heading."
    )
    # Already said by the model: left as written.
    said = "Data on other universities is not available in this platform."
    assert admit_missing(said, found) == said
    # Nothing missing: unchanged.
    assert admit_missing(drifted, {"topics": []}) == drifted
    assert admit_missing(drifted, None) == drifted
