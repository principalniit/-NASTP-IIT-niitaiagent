"""Application settings loaded from environment variables and an optional .env file."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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

    login_rate_limit_attempts: int = 5
    login_rate_limit_window_seconds: int = 300

    # Default crawler identity for new projects; editable per project.
    crawler_user_agent: str = "NIIT-SEO-Agent/0.1 (+https://niit.edu.pk)"

    ai_provider: Literal["none", "ollama"] = "none"
    ollama_base_url: str = "http://localhost:11434"

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
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
