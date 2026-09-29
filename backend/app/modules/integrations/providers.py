"""The integration types the platform knows about, with the settings each accepts.

Settings are validated per provider so that credentials cannot slip into the plain
settings field: anything secret goes through the encrypted secret field instead.
"""

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.validators import HttpsURL

Category = Literal["search_data", "analytics", "cms", "notifications"]


class _Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchConsoleConfig(_Config):
    property_url: str = Field(min_length=3, max_length=300, description="https://… or sc-domain:…")


class AnalyticsConfig(_Config):
    property_id: str = Field(pattern=r"^[0-9]{4,20}$", description="GA4 property id")


class WordPressConfig(_Config):
    site_url: HttpsURL
    username: str = Field(min_length=1, max_length=100)


class SmtpConfig(_Config):
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(default=587, ge=1, le=65535)
    username: str = Field(default="", max_length=200)
    from_address: EmailStr


class WebhookConfig(_Config):
    url: HttpsURL


@dataclass(frozen=True)
class Provider:
    key: str
    name: str
    category: Category
    description: str
    config: type[_Config]
    secret_label: str


PROVIDERS: dict[str, Provider] = {
    p.key: p
    for p in (
        Provider(
            "google_search_console",
            "Google Search Console",
            "search_data",
            "Search performance data (queries, clicks, impressions) for verified properties.",
            SearchConsoleConfig,
            "Service account key (JSON)",
        ),
        Provider(
            "google_analytics",
            "Google Analytics 4",
            "analytics",
            "Visitor analytics for a GA4 property.",
            AnalyticsConfig,
            "Service account key (JSON)",
        ),
        Provider(
            "wordpress",
            "WordPress",
            "cms",
            "Content management. Approved drafts could be published here in future, only with "
            "the owner's authorisation.",
            WordPressConfig,
            "Application password",
        ),
        Provider(
            "smtp_email",
            "Email (SMTP)",
            "notifications",
            "Email notifications such as report-ready and critical-issue alerts.",
            SmtpConfig,
            "SMTP password",
        ),
        Provider(
            "webhook",
            "Webhook",
            "notifications",
            "Send event notifications to another system.",
            WebhookConfig,
            "Signing secret",
        ),
    )
}


def validate_config(provider: str, config: dict[str, Any]) -> dict[str, Any]:
    return PROVIDERS[provider].config.model_validate(config).model_dump(mode="json")
