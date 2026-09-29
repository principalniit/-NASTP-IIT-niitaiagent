from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.monitoring.models import Frequency


class ScheduleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    frequency: Frequency = Frequency.WEEKLY
    hour: int = Field(default=2, ge=0, le=23, description="Hour of day, organisation time zone")


class ScheduleOut(BaseModel):
    enabled: bool
    frequency: Frequency
    hour: int
    timezone: str
    next_run_at: datetime | None
    last_run_at: datetime | None
    platform_enabled: bool = Field(
        description="False when the server's SCHEDULER_ENABLED switch is off; nothing runs then"
    )
