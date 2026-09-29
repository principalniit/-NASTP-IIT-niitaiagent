import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.pagination import PageParams
from app.core.request_context import RequestMeta
from app.core.urls import normalise_site_url
from app.modules.audit_logs import service as audit
from app.modules.organisations.dependencies import OrgAccess, ProjectAccess
from app.modules.organisations.models import Organisation
from app.modules.organisations.schemas import CrawlLimitCaps, OrganisationSettings
from app.modules.projects.models import Project, ProjectSettings
from app.modules.projects.schemas import (
    ProjectCreate,
    ProjectSettingsData,
    ProjectSort,
    ProjectUpdate,
    SortOrder,
)


def _caps(org: Organisation) -> CrawlLimitCaps:
    return OrganisationSettings.model_validate(org.settings).crawl_limits


def _cap_violations(data: ProjectSettingsData, caps: CrawlLimitCaps) -> list[dict[str, object]]:
    checks = [
        ("max_pages", data.crawl.max_pages, caps.max_pages),
        ("max_depth", data.crawl.max_depth, caps.max_depth),
        ("concurrency", data.crawl.concurrency, caps.max_concurrency),
    ]
    return [
        {"loc": ["settings", "crawl", field], "msg": f"Exceeds organisation limit of {limit}"}
        for field, value, limit in checks
        if value > limit
    ]


async def list_projects(
    session: AsyncSession,
    organisation_id: uuid.UUID,
    params: PageParams,
    q: str | None,
    sort: ProjectSort,
    order: SortOrder,
) -> tuple[list[Project], int]:
    query = select(Project).where(
        Project.organisation_id == organisation_id, Project.deleted_at.is_(None)
    )
    if q:
        escaped = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        query = query.where(
            or_(
                Project.name.ilike(pattern, escape="\\"), Project.domain.ilike(pattern, escape="\\")
            )
        )
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    column = {"name": Project.name, "created_at": Project.created_at, "domain": Project.domain}[
        sort
    ]
    query = query.order_by(column.asc() if order == "asc" else column.desc(), Project.id)
    rows = await session.scalars(query.offset(params.offset).limit(params.page_size))
    return list(rows), total


async def _commit_unique(session: AsyncSession) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError("A project for this domain already exists") from exc


async def create(
    session: AsyncSession, access: OrgAccess, data: ProjectCreate, meta: RequestMeta
) -> Project:
    root_url, domain = normalise_site_url(data.root_url)
    project = Project(
        organisation_id=access.organisation.id,
        name=data.name,
        root_url=root_url,
        domain=domain,
        description=data.description,
        created_by_id=access.user.id,
    )
    session.add(project)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError("A project for this domain already exists") from exc

    defaults = ProjectSettingsData()
    caps = _caps(access.organisation)
    defaults.crawl.max_pages = min(defaults.crawl.max_pages, caps.max_pages)
    defaults.crawl.max_depth = min(defaults.crawl.max_depth, caps.max_depth)
    defaults.crawl.concurrency = min(defaults.crawl.concurrency, caps.max_concurrency)
    session.add(
        ProjectSettings(
            project_id=project.id,
            organisation_id=project.organisation_id,
            settings=defaults.model_dump(mode="json"),
            updated_by_id=access.user.id,
        )
    )
    audit.record(
        session,
        action="project.created",
        actor_id=access.user.id,
        meta=meta,
        organisation_id=project.organisation_id,
        target_type="project",
        target_id=project.id,
        details={"name": project.name, "root_url": project.root_url},
    )
    await _commit_unique(session)
    await session.refresh(project)
    return project


async def update(
    session: AsyncSession, access: ProjectAccess, data: ProjectUpdate, meta: RequestMeta
) -> Project:
    project = access.project
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes:
        if changes["name"] is None:
            raise AppError("name cannot be null", code="validation_error")
        project.name = changes["name"]
    if "description" in changes:
        project.description = changes["description"]
    if "root_url" in changes:
        if changes["root_url"] is None:
            raise AppError("root_url cannot be null", code="validation_error")
        project.root_url, project.domain = normalise_site_url(changes["root_url"])
    audit.record(
        session,
        action="project.updated",
        actor_id=access.user.id,
        meta=meta,
        organisation_id=project.organisation_id,
        target_type="project",
        target_id=project.id,
        details={"fields": sorted(changes)},
    )
    await _commit_unique(session)
    await session.refresh(project)
    return project


async def soft_delete(session: AsyncSession, access: ProjectAccess, meta: RequestMeta) -> None:
    project = access.project
    project.deleted_at = datetime.now(UTC)
    audit.record(
        session,
        action="project.deleted",
        actor_id=access.user.id,
        meta=meta,
        organisation_id=project.organisation_id,
        target_type="project",
        target_id=project.id,
    )
    await session.commit()


async def get_settings_row(session: AsyncSession, project: Project) -> ProjectSettings:
    row = await session.get(ProjectSettings, project.id)
    if row is None or row.organisation_id != project.organisation_id:
        raise NotFoundError("Project settings not found")
    return row


async def update_settings(
    session: AsyncSession, access: ProjectAccess, data: ProjectSettingsData, meta: RequestMeta
) -> ProjectSettings:
    org = await session.get(Organisation, access.project.organisation_id)
    if org is None:
        raise NotFoundError("Project not found")
    violations = _cap_violations(data, _caps(org))
    if violations:
        raise AppError(
            "Crawl settings exceed organisation limits", code="validation_error", details=violations
        )
    row = await get_settings_row(session, access.project)
    row.settings = data.model_dump(mode="json")
    row.updated_by_id = access.user.id
    audit.record(
        session,
        action="project.settings_updated",
        actor_id=access.user.id,
        meta=meta,
        organisation_id=access.project.organisation_id,
        target_type="project",
        target_id=access.project.id,
    )
    await session.commit()
    await session.refresh(row)
    return row
