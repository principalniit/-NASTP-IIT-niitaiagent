import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str


class UserOut(UserSummary):
    is_active: bool
    is_platform_admin: bool
    created_at: datetime


PasswordField = Field(min_length=12, max_length=128)
