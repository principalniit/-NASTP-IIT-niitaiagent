import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.integrations.providers import PROVIDERS, Category


class ProviderOut(BaseModel):
    key: str
    name: str
    category: Category
    description: str
    config_schema: dict[str, Any]
    secret_label: str


class IntegrationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    name: str = Field(min_length=2, max_length=100)
    config: dict[str, Any] = Field(default_factory=dict)
    secret: str | None = Field(default=None, min_length=1, max_length=20_000)

    @field_validator("provider")
    @classmethod
    def _known(cls, value: str) -> str:
        if value not in PROVIDERS:
            raise ValueError(f"Unknown provider. Choose one of: {', '.join(PROVIDERS)}")
        return value


class IntegrationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=100)
    config: dict[str, Any] | None = None
    secret: str | None = Field(default=None, min_length=1, max_length=20_000)
    clear_secret: bool = False
    enabled: bool | None = None


class IntegrationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    name: str
    enabled: bool
    config: dict[str, Any]
    secret_set: bool
    secret_hint: str | None
    connected: bool = Field(
        default=False, description="Always false: the platform does not connect to providers yet"
    )
    created_at: datetime
    updated_at: datetime
