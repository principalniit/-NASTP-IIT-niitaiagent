import uuid

from pydantic import BaseModel, Field

from app.modules.organisations.models import OrgRole
from app.modules.users.schemas import PasswordField, UserOut


class LoginRequest(BaseModel):
    # Plain string, not EmailStr: validation differences must not reveal anything.
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth token type, not a secret
    expires_in: int


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = PasswordField


class MembershipOut(BaseModel):
    organisation_id: uuid.UUID
    organisation_name: str
    organisation_slug: str
    role: OrgRole
    permissions: list[str]


class MeResponse(BaseModel):
    user: UserOut
    memberships: list[MembershipOut]
