"""Application settings loaded from environment variables and an optional .env file."""

import logging
import secrets
from functools import lru_cache
from ipaddress import IPv4Network, IPv6Network, ip_network
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_METADATA_NET = ip_network("169.254.0.0/16")

# Values that must never sign tokens: the .env.example placeholder and an old default.
_KNOWN_WEAK_SECRETS = frozenset(
    {"replace-with-a-long-random-value", "dev-only-insecure-secret-change-me-0000000000"}
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    app_name: str = "NIIT AI SEO Agent"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://niit:niit@localhost:5432/niit_seo"

    # Required in production. Elsewhere, a missing or weak value is replaced by a random one
    # for the life of the process, so no fixed, published secret can ever sign tokens.
    jwt_secret: SecretStr = SecretStr("")
    jwt_issuer: str = "niit-seo-agent"
    jwt_audience: str = "niit-seo-agent-api"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 7
    cookie_secure: bool = False

    # Comma-separated list of allowed browser origins.
    cors_origins: str = "http://localhost:3000"
    # Only trust X-Forwarded-For when running behind a known reverse proxy.
    trust_proxy_headers: bool = False

    # Failed logins allowed per email and per client address within the window. The address
    # limit is higher because, without a trusted proxy, many users can share one address.
    login_rate_limit_attempts: int = 5
    login_rate_limit_ip_attempts: int = 20
    login_rate_limit_window_seconds: int = 300

    # Default crawler identity for new projects; editable per project.
    crawler_user_agent: str = "NIIT-SEO-Agent/0.1 (+https://niit.edu.pk)"
    # Comma-separated CIDR ranges the crawler may reach even though they are not public,
    # for example an on-premises staging server. Empty by default. Loopback and link-local
    # ranges are refused in production because they expose the host and cloud metadata.
    crawler_allowed_private_networks: str = ""
    crawler_max_response_bytes: int = 5_000_000
    crawler_max_redirects: int = 10
    crawler_max_sitemaps: int = 20
    crawler_max_sitemap_bytes: int = 50_000_000
    crawler_max_duration_seconds: int = 3600
    worker_poll_seconds: float = 2.0
    # A running crawl whose heartbeat is older than this is treated as abandoned.
    worker_stale_after_seconds: int = 300

    # Platform switch: "none" disables AI for every organisation regardless of their
    # settings. The Ollama address is operator-controlled and never set by tenants.
    ai_provider: Literal["none", "ollama"] = "none"
    ollama_base_url: str = "http://localhost:11434"
    ollama_default_model: str = ""
    ai_timeout_seconds: int = 180
    # Tokens the model reads per request. Set explicitly because some Ollama versions
    # default to a small window and silently cut off the end of long prompts.
    ai_context_tokens: int = 8192
    # How long Ollama keeps the model loaded after a task, as a duration with a unit ("30m",
    # "2h"; a negative value such as "-1m" keeps it until Ollama stops). Loading a model
    # takes seconds to minutes, so a quiet period longer than this makes the next task wait.
    ai_keep_alive: str = Field(default="30m", pattern=r"^-?\d{1,5}[smh]$")
    # Chromium executable for PDF reports. Empty uses Playwright's own installed browser.
    report_pdf_browser_path: str = ""
    # Scheduled crawls run only when this platform switch and the project's schedule are on.
    scheduler_enabled: bool = False
    # Comma-separated Fernet keys for integration credentials. The first key encrypts; all
    # keys decrypt, so a new key can be added in front and old secrets re-encrypted.
    # Generate one with: python -c "from cryptography.fernet import Fernet;
    # print(Fernet.generate_key().decode())"
    integrations_encryption_keys: SecretStr = SecretStr("")
    ai_max_active_jobs_per_org: int = 3

    # The dashboard's public address, used in links sent by email (invitations, resets).
    public_base_url: str = "http://localhost:3000"
    # Outgoing email through the organisation's own mail server. Empty host = email off:
    # invitations then give the administrator a link to share, and password resets go
    # through an administrator.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: str = ""
    smtp_starttls: bool = True
    invitation_ttl_days: int = 7
    password_reset_ttl_minutes: int = 60

    # Google endpoints for Search Console. Fixed by the operator, never by organisations;
    # changed only to point tests at a local fake.
    google_token_url: str = "https://oauth2.googleapis.com/token"  # noqa: S105 - an address
    google_search_console_url: str = "https://searchconsole.googleapis.com/webmasters/v3"
    # Days of Search Console data each sync imports (Google keeps 16 months).
    search_console_days: int = Field(default=90, ge=7, le=480)

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)

    @property
    def crawler_private_networks(self) -> list[IPv4Network | IPv6Network]:
        return [
            ip_network(part.strip(), strict=False)
            for part in self.crawler_allowed_private_networks.split(",")
            if part.strip()
        ]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def _check_encryption_keys(self) -> "Settings":
        from cryptography.fernet import Fernet

        for key in self.encryption_keys:
            try:
                Fernet(key)
            except ValueError as exc:
                raise ValueError(
                    "INTEGRATIONS_ENCRYPTION_KEYS must hold Fernet keys (32 url-safe base64 bytes)"
                ) from exc
        return self

    @property
    def encryption_keys(self) -> list[str]:
        raw = self.integrations_encryption_keys.get_secret_value()
        return [k.strip() for k in raw.split(",") if k.strip()]

    @model_validator(mode="after")
    def _check_production_safety(self) -> "Settings":
        secret = self.jwt_secret.get_secret_value()
        weak = secret in _KNOWN_WEAK_SECRETS or len(secret) < 32
        if weak and self.environment == "production":
            raise ValueError("JWT_SECRET must be set to a random value of 32+ characters")
        if weak:
            if self.environment != "test":
                logging.getLogger(__name__).warning(
                    "JWT_SECRET is not set or too weak; using a random secret for this process. "
                    "Sign-ins last until the API restarts. Set JWT_SECRET (see .env.example)."
                )
            self.jwt_secret = SecretStr(secrets.token_urlsafe(48))
        if self.environment == "production":
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in production")
            for net in self.crawler_private_networks:
                if net.is_loopback or net.is_link_local or net.overlaps(_METADATA_NET):
                    raise ValueError(
                        "CRAWLER_ALLOWED_PRIVATE_NETWORKS must not include loopback or "
                        "link-local ranges in production"
                    )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
