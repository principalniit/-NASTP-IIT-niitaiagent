"""Plans: named sets of usage limits assigned to organisations. No prices, no payments."""

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UUIDPrimaryKey


class Plan(UUIDPrimaryKey, Base):
    __tablename__ = "plans"
    __table_args__ = (
        # At most one default plan.
        Index(
            "uq_plans_single_default",
            "is_default",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )

    key: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    # Validated through PlanLimits; a missing or null limit means unlimited.
    limits: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
