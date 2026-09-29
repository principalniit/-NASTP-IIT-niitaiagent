"""Integration records. Credentials are encrypted at rest and never returned."""

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.core.errors import AppError
from app.core.request_context import RequestMeta
from app.modules.audit_logs import service as audit
from app.modules.integrations.models import Integration
from app.modules.integrations.providers import PROVIDERS, validate_config
from app.modules.integrations.schemas import (
    IntegrationCreate,
    IntegrationOut,
    IntegrationUpdate,
    ProviderOut,
)
from app.modules.organisations.dependencies import IntegrationAccess, OrgAccess


def providers() -> list[ProviderOut]:
    return [
        ProviderOut(
            key=p.key,
            name=p.name,
            category=p.category,
            description=p.description,
            config_schema=p.config.model_json_schema(),
            secret_label=p.secret_label,
        )
        for p in PROVIDERS.values()
    ]


def to_out(integration: Integration) -> IntegrationOut:
    return IntegrationOut(
        id=integration.id,
        provider=integration.provider,
        name=integration.name,
        enabled=integration.enabled,
        config=integration.config,
        secret_set=integration.secret_hint is not None,
        secret_hint=integration.secret_hint,
        created_at=integration.created_at,
        updated_at=integration.updated_at,
    )


def _config(provider: str, config: dict[str, object]) -> dict[str, object]:
    try:
        return validate_config(provider, config)
    except ValidationError as exc:
        raise AppError(
            "Invalid settings for this integration",
            code="validation_error",
            details=[{"loc": ["config", *e["loc"]], "msg": e["msg"]} for e in exc.errors()],
        ) from exc


def _hint(secret: str) -> str:
    return "…" + secret[-4:] if len(secret) >= 12 else "set"


def _set_secret(integration: Integration, secret: str) -> None:
    integration.secret = crypto.encrypt(secret)
    integration.secret_hint = _hint(secret)


def _audit(
    session: AsyncSession,
    integration: Integration,
    action: str,
    access: OrgAccess | IntegrationAccess,
    meta: RequestMeta,
    details: dict[str, object],
) -> None:
    audit.record(
        session,
        action=f"integration.{action}",
        actor_id=access.user.id,
        meta=meta,
        organisation_id=integration.organisation_id,
        target_type="integration",
        target_id=integration.id,
        details={"provider": integration.provider, **details},
    )


async def list_integrations(session: AsyncSession, access: OrgAccess) -> list[IntegrationOut]:
    rows = await session.scalars(
        select(Integration)
        .where(Integration.organisation_id == access.organisation.id)
        .order_by(Integration.created_at)
    )
    return [to_out(i) for i in rows]


async def create(
    session: AsyncSession, access: OrgAccess, body: IntegrationCreate, meta: RequestMeta
) -> IntegrationOut:
    integration = Integration(
        organisation_id=access.organisation.id,
        provider=body.provider,
        name=body.name,
        enabled=False,
        config=_config(body.provider, body.config),
        created_by_id=access.user.id,
    )
    if body.secret:
        _set_secret(integration, body.secret)
    session.add(integration)
    await session.flush()
    _audit(session, integration, "created", access, meta, {"credential_set": bool(body.secret)})
    await session.commit()
    await session.refresh(integration)
    return to_out(integration)


async def update(
    session: AsyncSession, access: IntegrationAccess, body: IntegrationUpdate, meta: RequestMeta
) -> IntegrationOut:
    integration = access.integration
    changed: dict[str, object] = {}
    if body.name is not None:
        integration.name = body.name
        changed["name"] = body.name
    if body.config is not None:
        integration.config = _config(integration.provider, body.config)
        changed["config"] = "updated"
    if body.secret:
        _set_secret(integration, body.secret)
        changed["credential"] = "replaced"
    elif body.clear_secret:
        integration.secret, integration.secret_hint = None, None
        changed["credential"] = "cleared"
    if body.enabled is not None:
        integration.enabled = body.enabled
        changed["enabled"] = body.enabled
    _audit(session, integration, "updated", access, meta, changed)
    await session.commit()
    await session.refresh(integration)
    return to_out(integration)


async def delete(session: AsyncSession, access: IntegrationAccess, meta: RequestMeta) -> None:
    _audit(session, access.integration, "deleted", access, meta, {"name": access.integration.name})
    await session.delete(access.integration)
    await session.commit()
