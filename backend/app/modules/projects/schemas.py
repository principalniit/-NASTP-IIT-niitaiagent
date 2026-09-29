import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.core.config import get_settings
from app.core.validators import Hostname, HttpsURL, ShortText, SiteURL


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _path_pattern(value: str) -> str:
    value = value.strip()
    if not value.startswith("/"):
        raise ValueError("Path patterns must start with '/'")
    return value


def _page_ref(value: str) -> str:
    value = value.strip()
    if value.startswith("/"):
        return value
    if value.startswith(("http://", "https://")):
        return value
    raise ValueError("Use a path starting with '/' or an absolute http(s) URL")


PathPattern = Annotated[str, Field(max_length=500), AfterValidator(_path_pattern)]
PageRef = Annotated[str, Field(max_length=2048), AfterValidator(_page_ref)]


class CrawlSettings(_Strict):
    max_pages: int = Field(default=100, ge=1, le=10_000)
    max_depth: int = Field(default=5, ge=0, le=50)
    concurrency: int = Field(default=2, ge=1, le=20)
    timeout_seconds: int = Field(default=15, ge=1, le=120)
    delay_ms: int = Field(default=1000, ge=0, le=60_000)
    user_agent: str = Field(
        default_factory=lambda: get_settings().crawler_user_agent, min_length=3, max_length=300
    )
    render_javascript: bool = False


class PageGroup(_Strict):
    name: ShortText
    patterns: list[PathPattern] = Field(min_length=1, max_length=50)


class ContentType(_Strict):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,49}$")
    label: ShortText
    url_patterns: list[PathPattern] = Field(default_factory=list, max_length=50)
    expected_sections: list[str] = Field(default_factory=list, max_length=30)


class ApprovedSource(_Strict):
    label: ShortText
    url: HttpsURL


class ContactInfo(_Strict):
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=500)


class InstitutionalProfile(_Strict):
    description: str | None = Field(default=None, max_length=5000)
    contact: ContactInfo = Field(default_factory=ContactInfo)
    approved_sources: list[ApprovedSource] = Field(default_factory=list, max_length=50)


class ProjectSettingsData(_Strict):
    crawl: CrawlSettings = Field(default_factory=CrawlSettings)
    allowed_extra_hosts: list[Hostname] = Field(default_factory=list, max_length=20)
    excluded_paths: list[PathPattern] = Field(default_factory=list, max_length=200)
    important_pages: list[PageRef] = Field(default_factory=list, max_length=500)
    page_groups: list[PageGroup] = Field(default_factory=list, max_length=50)
    content_types: list[ContentType] = Field(default_factory=list, max_length=50)
    institutional_profile: InstitutionalProfile = Field(default_factory=InstitutionalProfile)
    editorial_approval_required: bool = True

    @model_validator(mode="after")
    def _unique_keys(self) -> "ProjectSettingsData":
        keys = [c.key for c in self.content_types]
        if len(keys) != len(set(keys)):
            raise ValueError("Content type keys must be unique")
        names = [g.name for g in self.page_groups]
        if len(names) != len(set(names)):
            raise ValueError("Page group names must be unique")
        return self


class ProjectCreate(_Strict):
    name: ShortText
    root_url: SiteURL
    description: str | None = Field(default=None, max_length=2000)


class ProjectUpdate(_Strict):
    name: ShortText | None = None
    root_url: SiteURL | None = None
    description: str | None = Field(default=None, max_length=2000)


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organisation_id: uuid.UUID
    name: str
    root_url: str
    domain: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class ProjectSettingsOut(BaseModel):
    project_id: uuid.UUID
    settings: ProjectSettingsData
    updated_at: datetime


ProjectSort = Literal["name", "created_at", "domain"]
SortOrder = Literal["asc", "desc"]
