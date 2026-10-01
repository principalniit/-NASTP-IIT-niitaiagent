import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modules.organisations.models import OrgRole
from app.modules.users.schemas import PasswordField


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InvitationCreate(_Strict):
    email: EmailStr
    role: OrgRole


class InvitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: OrgRole
    expires_at: datetime
    created_at: datetime


class InvitationCreated(BaseModel):
    invitation: InvitationOut
    # Shown once, so an administrator can share it when email is not set up.
    invite_url: str
    email_sent: bool


class TokenBody(_Strict):
    token: str = Field(min_length=20, max_length=200)


class InvitationPreview(BaseModel):
    organisation_name: str
    email: str
    role: OrgRole
    expires_at: datetime
    account_exists: bool


class AcceptNew(_Strict):
    token: str = Field(min_length=20, max_length=200)
    full_name: str = Field(min_length=1, max_length=200)
    password: str = PasswordField


class Accepted(BaseModel):
    organisation_id: uuid.UUID
    email: str
