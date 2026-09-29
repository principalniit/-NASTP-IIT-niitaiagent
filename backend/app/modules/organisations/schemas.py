import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.validators import (
    HexColour,
    Hostname,
    HttpsURL,
    LanguageCode,
    ShortText,
    Slug,
    TimeZone,
)
from app.modules.organisations.models import OrgRole
from app.modules.users.schemas import UserSummary


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TerminologyEntry(_Strict):
    preferred: str = Field(min_length=1, max_length=120)
    avoid: list[str] = Field(default_factory=list, max_length=20)
    note: str | None = Field(default=None, max_length=500)


class AISettings(_Strict):
    provider: Literal["none", "ollama"] = "none"
    model: str | None = Field(default=None, max_length=100)


class CrawlLimitCaps(_Strict):
    """Organisation-wide ceilings that project crawl settings cannot exceed."""

    max_pages: int = Field(default=500, ge=1, le=10_000)
    max_depth: int = Field(default=10, ge=0, le=50)
    max_concurrency: int = Field(default=5, ge=1, le=20)


class ReportBranding(_Strict):
    primary_colour: HexColour | None = None
    footer_text: str | None = Field(default=None, max_length=300)
    # White-label: the name reports show instead of the organisation's own name, and an
    # optional line on the cover such as "Prepared by the web team for the Board".
    display_name: str | None = Field(default=None, max_length=200)
    cover_note: str | None = Field(default=None, max_length=300)


class DataRetention(_Strict):
    """Off by default: nothing is deleted unless an owner sets these."""

    # Keep full page data for this many most recent crawls per project. Older crawls keep
    # their summary, score and issues; their page-level data is deleted.
    keep_crawls: int | None = Field(default=None, ge=2, le=1000)
    delete_reports_after_days: int | None = Field(default=None, ge=30, le=3650)


NotificationEvent = Literal["crawl_completed", "critical_issue_detected", "report_ready"]


class NotificationPreferences(_Strict):
    enabled: bool = False
    events: list[NotificationEvent] = Field(default_factory=list)


class OrganisationSettings(_Strict):
    brand_tone: str | None = Field(default=None, max_length=1000)
    approved_terminology: list[TerminologyEntry] = Field(default_factory=list, max_length=200)
    ai: AISettings = Field(default_factory=AISettings)
    crawl_limits: CrawlLimitCaps = Field(default_factory=CrawlLimitCaps)
    report_branding: ReportBranding = Field(default_factory=ReportBranding)
    notifications: NotificationPreferences = Field(default_factory=NotificationPreferences)
    data_retention: DataRetention = Field(default_factory=DataRetention)


class OrganisationCreate(_Strict):
    name: ShortText
    slug: Slug | None = None
    domain: Hostname | None = None
    logo_url: HttpsURL | None = None
    timezone: TimeZone = "UTC"
    language: LanguageCode = "en"


class OrganisationUpdate(_Strict):
    name: ShortText | None = None
    domain: Hostname | None = None
    logo_url: HttpsURL | None = None
    timezone: TimeZone | None = None
    language: LanguageCode | None = None
    settings: OrganisationSettings | None = None


class OrganisationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    domain: str | None
    logo_url: str | None
    timezone: str
    language: str
    settings: OrganisationSettings
    is_active: bool
    created_at: datetime
    updated_at: datetime
    my_role: OrgRole | None = None
    my_permissions: list[str] = Field(default_factory=list)


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user: UserSummary
    role: OrgRole
    created_at: datetime


class MemberCreate(_Strict):
    email: EmailStr
    role: OrgRole
    # Required only when no account exists for the email yet.
    full_name: ShortText | None = None
    password: str | None = Field(default=None, min_length=12, max_length=128)


class MemberUpdate(_Strict):
    role: OrgRole
