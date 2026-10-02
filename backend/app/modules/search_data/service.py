"""Importing and reading Search Console data.

A sync replaces the imported period for its integration: page-days in the period are
deleted and re-inserted (so late, revised figures from Google are picked up), and the
query table keeps only the latest period. Project views select rows by the page's host.
Every figure shown is a sum or an impressions-weighted average of what Google reported.
"""

import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import crypto
from app.core.config import get_settings
from app.core.database import get_session_factory
from app.core.errors import AppError, ConflictError
from app.core.request_context import RequestMeta
from app.modules.audit_logs import service as audit
from app.modules.integrations.models import Integration
from app.modules.organisations.dependencies import IntegrationAccess
from app.modules.projects.models import Project
from app.modules.search_data import google
from app.modules.search_data.models import (
    SearchPageDay,
    SearchPageQuery,
    SearchSync,
    SyncStatus,
)

logger = logging.getLogger(__name__)

PROVIDER = "google_search_console"
MAX_PAGE_DAY_ROWS = 200_000
MAX_QUERY_ROWS = 50_000
INSERT_CHUNK = 5_000
AUTO_SYNC_EVERY = timedelta(hours=20)


def _require_search_console(integration: Integration) -> None:
    if integration.provider != PROVIDER:
        raise AppError("This integration is not Google Search Console", code="wrong_provider")


async def _key(session: AsyncSession, integration: Integration) -> google.ServiceAccountKey:
    await session.refresh(integration, ["secret"])
    if integration.secret is None:
        raise ConflictError(
            "Save the service account JSON key for this integration first.", code="no_credential"
        )
    try:
        return google.parse_key(crypto.decrypt(integration.secret))
    except ValueError as exc:
        raise ConflictError(str(exc), code="credential_unreadable") from exc


def _property(integration: Integration) -> str:
    return str(integration.config.get("property_url", ""))


async def test_connection(session: AsyncSession, access: IntegrationAccess) -> dict[str, str]:
    integration = access.integration
    _require_search_console(integration)
    key = await _key(session, integration)
    try:
        level = await google.check_property(key, _property(integration))
    except google.SearchConsoleError as exc:
        raise AppError(str(exc), code="search_console_error") from exc
    return {"permission_level": level, "service_account_email": key.client_email}


async def request_sync(
    session: AsyncSession, access: IntegrationAccess, meta: RequestMeta
) -> SearchSync:
    integration = access.integration
    _require_search_console(integration)
    await _key(session, integration)  # fail now, not in the worker, when no key is saved
    if await _active_sync(session, integration.id):
        raise ConflictError("A sync of this integration is already queued or running")
    sync = SearchSync(
        organisation_id=integration.organisation_id,
        integration_id=integration.id,
        status=SyncStatus.QUEUED,
        requested_by_id=access.user.id,
    )
    session.add(sync)
    await session.flush()
    audit.record(
        session,
        action="search_console.sync_requested",
        actor_id=access.user.id,
        meta=meta,
        organisation_id=integration.organisation_id,
        target_type="integration",
        target_id=integration.id,
    )
    await session.commit()
    await session.refresh(sync)
    return sync


async def _active_sync(session: AsyncSession, integration_id: uuid.UUID) -> bool:
    found = await session.scalar(
        select(SearchSync.id).where(
            SearchSync.integration_id == integration_id,
            SearchSync.status.in_([SyncStatus.QUEUED, SyncStatus.RUNNING]),
        )
    )
    return found is not None


async def latest_syncs(session: AsyncSession, integration: Integration) -> list[SearchSync]:
    rows = await session.scalars(
        select(SearchSync)
        .where(
            SearchSync.integration_id == integration.id,
            SearchSync.organisation_id == integration.organisation_id,
        )
        .order_by(SearchSync.created_at.desc())
        .limit(10)
    )
    return list(rows)


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()[:253]


def _period(today: date) -> tuple[date, date]:
    end = today - timedelta(days=1)
    return end - timedelta(days=get_settings().search_console_days - 1), end


async def _insert(session: AsyncSession, model: type, rows: list[dict[str, Any]]) -> None:
    for i in range(0, len(rows), INSERT_CHUNK):
        await session.execute(insert(model), rows[i : i + INSERT_CHUNK])


async def run_sync(
    sync_id: uuid.UUID, *, factory: async_sessionmaker[AsyncSession] | None = None
) -> SyncStatus:
    factory = factory or get_session_factory()
    async with factory() as session:
        sync = await session.get(SearchSync, sync_id)
        if sync is None:
            raise LookupError(f"Search sync {sync_id} not found")
        integration = await session.get(Integration, sync.integration_id)
        sync.started_at = datetime.now(UTC)
        start, end = _period(datetime.now(UTC).date())
        sync.start_date, sync.end_date = start, end
        try:
            if integration is None:
                raise google.SearchConsoleError("The integration no longer exists.")
            key = await _key(session, integration)
            prop = _property(integration)
            days = await google.query(key, prop, start, end, ["date", "page"], MAX_PAGE_DAY_ROWS)
            queries = await google.query(key, prop, start, end, ["page", "query"], MAX_QUERY_ROWS)
        except (google.SearchConsoleError, ConflictError) as exc:
            sync.status, sync.error = SyncStatus.FAILED, str(exc)
            sync.finished_at = datetime.now(UTC)
            await session.commit()
            return sync.status

        scope = {"organisation_id": sync.organisation_id, "integration_id": sync.integration_id}
        day_rows = [
            {
                **scope,
                "day": date.fromisoformat(r["keys"][0]),
                "page": r["keys"][1][:2048],
                "page_host": _host(r["keys"][1]),
                "clicks": int(r.get("clicks", 0)),
                "impressions": int(r.get("impressions", 0)),
                "position": float(r.get("position", 0.0)),
            }
            for r in days
            if len(r.get("keys", [])) == 2
        ]
        query_rows = [
            {
                **scope,
                "sync_id": sync.id,
                "page": r["keys"][0][:2048],
                "page_host": _host(r["keys"][0]),
                "query": r["keys"][1][:500],
                "clicks": int(r.get("clicks", 0)),
                "impressions": int(r.get("impressions", 0)),
                "position": float(r.get("position", 0.0)),
            }
            for r in queries
            if len(r.get("keys", [])) == 2
        ]
        await session.execute(
            delete(SearchPageDay).where(
                SearchPageDay.integration_id == sync.integration_id,
                SearchPageDay.day >= start,
                SearchPageDay.day <= end,
            )
        )
        await session.execute(
            delete(SearchPageQuery).where(SearchPageQuery.integration_id == sync.integration_id)
        )
        await _insert(session, SearchPageDay, day_rows)
        await _insert(session, SearchPageQuery, query_rows)
        sync.page_day_rows, sync.query_rows = len(day_rows), len(query_rows)
        sync.status, sync.finished_at = SyncStatus.SUCCEEDED, datetime.now(UTC)
        await session.commit()
        logger.info(
            "Search Console sync finished",
            extra={"sync_id": str(sync.id), "page_days": len(day_rows), "queries": len(query_rows)},
        )
        return sync.status


async def queue_due_syncs(factory: async_sessionmaker[AsyncSession]) -> int:
    """Queue a daily sync for each enabled Search Console integration with a saved key."""
    queued = 0
    cutoff = datetime.now(UTC) - AUTO_SYNC_EVERY
    async with factory() as session:
        integrations = await session.scalars(
            select(Integration).where(
                Integration.provider == PROVIDER,
                Integration.enabled.is_(True),
                Integration.secret_hint.is_not(None),
            )
        )
        for integration in integrations:
            recent = await session.scalar(
                select(SearchSync.id).where(
                    SearchSync.integration_id == integration.id,
                    SearchSync.created_at > cutoff,
                )
            )
            if recent is None and not await _active_sync(session, integration.id):
                session.add(
                    SearchSync(
                        organisation_id=integration.organisation_id,
                        integration_id=integration.id,
                        status=SyncStatus.QUEUED,
                    )
                )
                queued += 1
        await session.commit()
    return queued


# ---------------------------------------------------------------------------------------
# Reading data for a project


def project_hosts(project: Project) -> list[str]:
    host = _host(project.root_url)
    bare = host.removeprefix("www.")
    return sorted({bare, f"www.{bare}"})


def _weighted_position(position_x_impressions: float | None, impressions: int) -> float | None:
    if not impressions or position_x_impressions is None:
        return None
    return round(position_x_impressions / impressions, 1)


def _ctr(clicks: int, impressions: int) -> float | None:
    return round(clicks / impressions, 4) if impressions else None


async def connection_state(session: AsyncSession, project: Project) -> dict[str, Any]:
    # Only records with a validated service account key count. Records made before the
    # connection existed hold whatever was typed then (for example an email as the
    # property, or a password), and cannot reach Google.
    integrations = [
        i
        for i in await session.scalars(
            select(Integration).where(
                Integration.organisation_id == project.organisation_id,
                Integration.provider == PROVIDER,
            )
        )
        if i.secret_hint and i.config.get("service_account_email")
    ]
    last = None
    if integrations:
        last = await session.scalar(
            select(func.max(SearchSync.finished_at)).where(
                SearchSync.integration_id.in_([i.id for i in integrations]),
                SearchSync.status == SyncStatus.SUCCEEDED,
            )
        )
    return {
        "connected": bool(integrations),
        "properties": [_property(i) for i in integrations],
        "last_synced_at": last,
    }


async def performance(session: AsyncSession, project: Project, days: int) -> dict[str, Any]:
    state = await connection_state(session, project)
    hosts = project_hosts(project)
    scope = (
        SearchPageDay.organisation_id == project.organisation_id,
        SearchPageDay.page_host.in_(hosts),
    )
    latest: date | None = await session.scalar(select(func.max(SearchPageDay.day)).where(*scope))
    if latest is None:
        return {**state, "state": "not_connected" if not state["connected"] else "no_data"}
    start = latest - timedelta(days=days - 1)
    in_window = (*scope, SearchPageDay.day >= start)
    weighted = func.sum(SearchPageDay.position * SearchPageDay.impressions)
    clicks, impressions, pos = (
        await session.execute(
            select(
                func.coalesce(func.sum(SearchPageDay.clicks), 0),
                func.coalesce(func.sum(SearchPageDay.impressions), 0),
                weighted,
            ).where(*in_window)
        )
    ).one()
    daily = (
        await session.execute(
            select(
                SearchPageDay.day,
                func.sum(SearchPageDay.clicks),
                func.sum(SearchPageDay.impressions),
            )
            .where(*in_window)
            .group_by(SearchPageDay.day)
            .order_by(SearchPageDay.day)
        )
    ).all()
    pages = (
        await session.execute(
            select(
                SearchPageDay.page,
                func.sum(SearchPageDay.clicks).label("c"),
                func.sum(SearchPageDay.impressions).label("i"),
                weighted,
            )
            .where(*in_window)
            .group_by(SearchPageDay.page)
            .order_by(
                func.sum(SearchPageDay.clicks).desc(), func.sum(SearchPageDay.impressions).desc()
            )
            .limit(20)
        )
    ).all()
    return {
        **state,
        "state": "ready",
        "start": start,
        "end": latest,
        "totals": {
            "clicks": int(clicks),
            "impressions": int(impressions),
            "ctr": _ctr(int(clicks), int(impressions)),
            "position": _weighted_position(pos, int(impressions)),
        },
        "daily": [
            {"day": d, "clicks": int(c or 0), "impressions": int(i or 0)} for d, c, i in daily
        ],
        "top_pages": [
            {
                "page": page,
                "clicks": int(c or 0),
                "impressions": int(i or 0),
                "ctr": _ctr(int(c or 0), int(i or 0)),
                "position": _weighted_position(w, int(i or 0)),
            }
            for page, c, i, w in pages
        ],
        "top_queries": await _top_queries(session, project, hosts, None),
    }


async def _top_queries(
    session: AsyncSession, project: Project, hosts: list[str], page: str | None, limit: int = 20
) -> list[dict[str, Any]]:
    conditions = [
        SearchPageQuery.organisation_id == project.organisation_id,
        SearchPageQuery.page_host.in_(hosts),
    ]
    if page is not None:
        conditions.append(SearchPageQuery.page == page)
    weighted = func.sum(SearchPageQuery.position * SearchPageQuery.impressions)
    rows = (
        await session.execute(
            select(
                SearchPageQuery.query,
                func.sum(SearchPageQuery.clicks),
                func.sum(SearchPageQuery.impressions),
                weighted,
            )
            .where(*conditions)
            .group_by(SearchPageQuery.query)
            .order_by(
                func.sum(SearchPageQuery.clicks).desc(),
                func.sum(SearchPageQuery.impressions).desc(),
            )
            .limit(limit)
        )
    ).all()
    return [
        {
            "query": q,
            "clicks": int(c or 0),
            "impressions": int(i or 0),
            "ctr": _ctr(int(c or 0), int(i or 0)),
            "position": _weighted_position(w, int(i or 0)),
        }
        for q, c, i, w in rows
    ]


async def page_performance(
    session: AsyncSession, project: Project, url: str, days: int
) -> dict[str, Any]:
    hosts = project_hosts(project)
    if _host(url) not in hosts:
        return {"state": "no_data"}
    scope = (
        SearchPageDay.organisation_id == project.organisation_id,
        SearchPageDay.page_host.in_(hosts),
    )
    latest: date | None = await session.scalar(select(func.max(SearchPageDay.day)).where(*scope))
    if latest is None:
        return {"state": "no_data"}
    start = latest - timedelta(days=days - 1)
    clicks, impressions, weighted = (
        await session.execute(
            select(
                func.coalesce(func.sum(SearchPageDay.clicks), 0),
                func.coalesce(func.sum(SearchPageDay.impressions), 0),
                func.sum(SearchPageDay.position * SearchPageDay.impressions),
            ).where(*scope, SearchPageDay.page == url, SearchPageDay.day >= start)
        )
    ).one()
    return {
        "state": "ready",
        "start": start,
        "end": latest,
        "totals": {
            "clicks": int(clicks),
            "impressions": int(impressions),
            "ctr": _ctr(int(clicks), int(impressions)),
            "position": _weighted_position(weighted, int(impressions)),
        },
        "top_queries": await _top_queries(session, project, hosts, url, limit=10),
    }


async def ai_evidence(session: AsyncSession, project: Project) -> dict[str, Any] | None:
    """A compact summary for the AI assistant, or None when there is no data."""
    data = await performance(session, project, 28)
    if data["state"] != "ready":
        return None

    def with_percent(row: dict[str, Any]) -> dict[str, Any]:
        # The model writes rates as percentages; give it the exact figure to quote.
        ctr = row.get("ctr")
        return {**row, "ctr_percent": round(ctr * 100, 1) if ctr is not None else None}

    data["totals"] = with_percent(data["totals"])
    data["top_pages"] = [with_percent(r) for r in data["top_pages"]]
    data["top_queries"] = [with_percent(r) for r in data["top_queries"]]
    return {
        "source": "Google Search Console",
        "period": {"start": data["start"].isoformat(), "end": data["end"].isoformat()},
        "note": "Clicks and impressions from Google Search only, not all visitors. Position is "
        "Google's average position weighted by impressions (1 is the top).",
        "totals": data["totals"],
        "top_pages": data["top_pages"][:10],
        "top_queries": data["top_queries"][:10],
    }
