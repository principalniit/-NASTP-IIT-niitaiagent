import enum
import uuid
from typing import Any

from sqlalchemy import Boolean, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, Timestamps, UUIDPrimaryKey
from app.modules.users.models import User


class OrgRole(enum.StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    SEO_MANAGER = "seo_manager"
    EDITOR = "editor"
    VIEWER = "viewer"


class Organisation(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "organisations"

    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    domain: Mapped[str | None] = mapped_column(String(253))
    logo_url: Mapped[str | None] = mapped_column(String(2048))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    language: Mapped[str] = mapped_column(String(16), default="en")
    # Validated through OrganisationSettings before every write.
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    # None follows the default plan.
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("plans.id", ondelete="SET NULL"), index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class OrganisationMember(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "organisation_members"
    __table_args__ = (UniqueConstraint("organisation_id", "user_id"),)

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[OrgRole] = mapped_column(
        Enum(
            OrgRole,
            name="org_role",
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=lambda e: [m.value for m in e],
        )
    )

    user: Mapped[User] = relationship(lazy="joined")
