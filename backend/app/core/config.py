"""Application settings loaded from environment variables and an optional .env file."""

from functools import lru_cache
from ipaddress import IPv4Network, IPv6Network, ip_network
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_METADATA_NET = ip_network("169.254.0.0/16")

DEV_JWT_SECRET = "dev-only-insecure-secret-change-me-0000000000"  # noqa: S105


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    app_name: str = "NIIT AI SEO Agent"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://niit:niit@localhost:5432/niit_seo"

    jwt_secret: SecretStr = SecretStr(DEV_JWT_SECRET)
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
    ai_max_active_jobs_per_org: int = 3

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
    def _check_production_safety(self) -> "Settings":
        if self.environment == "production":
            secret = self.jwt_secret.get_secret_value()
            if secret == DEV_JWT_SECRET or len(secret) < 32:
                raise ValueError("JWT_SECRET must be set to a random value of 32+ characters")
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
