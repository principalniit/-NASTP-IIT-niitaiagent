import pytest
from pydantic import ValidationError

from app.modules.organisations.schemas import OrganisationCreate, OrganisationSettings
from app.modules.projects.schemas import ProjectSettingsData


def test_project_defaults_match_brief() -> None:
    data = ProjectSettingsData()
    assert data.crawl.max_pages == 100
    assert data.crawl.max_depth == 5
    assert data.crawl.render_javascript is False
    assert data.editorial_approval_required is True
    assert data.content_types == []


def test_project_settings_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ProjectSettingsData.model_validate({"crawl": {"max_pages": 10, "ignore_robots": True}})


@pytest.mark.parametrize(
    "payload",
    [
        {"crawl": {"max_pages": 0}},
        {"crawl": {"concurrency": 100}},
        {"excluded_paths": ["admin/*"]},
        {"allowed_extra_hosts": ["10.0.0.1"]},
        {"allowed_extra_hosts": ["localhost"]},
        {"important_pages": ["javascript:alert(1)"]},
        {"content_types": [{"key": "a", "label": "A"}, {"key": "a", "label": "B"}]},
        {"content_types": [{"key": "Bad Key", "label": "A"}]},
        {"institutional_profile": {"approved_sources": [{"label": "x", "url": "http://a.org"}]}},
    ],
)
def test_project_settings_validation(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ProjectSettingsData.model_validate(payload)


def test_project_settings_accept_valid_institutional_config() -> None:
    data = ProjectSettingsData.model_validate(
        {
            "allowed_extra_hosts": ["Admissions.Example.org"],
            "excluded_paths": ["/wp-admin/*"],
            "important_pages": ["/admissions", "https://example.org/programmes"],
            "page_groups": [{"name": "Programmes", "patterns": ["/programmes/*"]}],
            "content_types": [{"key": "admissions", "label": "Admissions"}],
        }
    )
    assert data.allowed_extra_hosts == ["admissions.example.org"]


def test_organisation_validation() -> None:
    with pytest.raises(ValidationError):
        OrganisationCreate(name="X", timezone="Mars/Olympus")
    with pytest.raises(ValidationError):
        OrganisationCreate(name="X", logo_url="http://example.org/logo.png")
    with pytest.raises(ValidationError):
        OrganisationSettings.model_validate({"ai": {"provider": "openai"}})
    org = OrganisationCreate(name="X", timezone="Asia/Karachi", domain="https://Example.org/")
    assert org.domain == "example.org"
