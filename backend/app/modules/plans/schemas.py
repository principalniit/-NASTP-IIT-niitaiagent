import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Resource = Literal[
    "projects", "members", "crawls_per_month", "ai_tasks_per_day", "reports_per_month"
]


class PlanLimits(BaseModel):
    """Usage limits. None means no limit from the plan (platform caps still apply)."""

    model_config = ConfigDict(extra="forbid")

    max_projects: int | None = Field(default=None, ge=1, le=100_000)
    max_members: int | None = Field(default=None, ge=1, le=100_000)
    max_pages_per_crawl: int | None = Field(default=None, ge=1, le=1_000_000)
    max_crawls_per_month: int | None = Field(default=None, ge=1, le=100_000)
    max_ai_tasks_per_day: int | None = Field(default=None, ge=1, le=100_000)
    max_reports_per_month: int | None = Field(default=None, ge=1, le=100_000)


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    name: str
    description: str | None
    limits: PlanLimits
    is_default: bool
    updated_at: datetime


class PlanCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=40)
    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    limits: PlanLimits = Field(default_factory=PlanLimits)


class PlanUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    limits: PlanLimits | None = None
    is_default: bool | None = Field(default=None, description="Only true is accepted")


class PlanAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_key: str = Field(max_length=40)


class UsageItem(BaseModel):
    used: int
    limit: int | None


class UsageOut(BaseModel):
    plan: PlanOut
    plan_assigned: bool = Field(description="False when the organisation follows the default plan")
    usage: dict[Resource, UsageItem]
    max_pages_per_crawl: int | None
    month_starts: datetime
    day_starts: datetime
