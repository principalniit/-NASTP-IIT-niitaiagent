"""Authorisation dependencies. Every tenant-scoped route goes through one of these."""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.errors import ForbiddenError, NotFoundError
from app.modules.auth.dependencies import get_current_user
from app.modules.crawler.models import CrawlJob
from app.modules.organisations.models import Organisation, OrganisationMember, OrgRole
from app.modules.organisations.permissions import (
    PLATFORM_ADMIN_PERMISSIONS,
    Permission,
    role_has,
)
from app.modules.projects.models import Project
from app.modules.seo.models import SeoIssue
from app.modules.users.models import User


@dataclass(frozen=True)
class OrgAccess:
    user: User
    organisation: Organisation
    # None when a platform administrator acts without being a member.
    role: OrgRole | None

    @property
    def is_owner_level(self) -> bool:
        return self.role == OrgRole.OWNER or (self.role is None and self.user.is_platform_admin)


@dataclass(frozen=True)
class ProjectAccess:
    user: User
    project: Project
    role: OrgRole


@dataclass(frozen=True)
class CrawlAccess:
    user: User
    crawl: CrawlJob
    project: Project
    role: OrgRole


@dataclass(frozen=True)
class IssueAccess:
    user: User
    issue: SeoIssue
    project: Project
    role: OrgRole


async def get_membership(
    session: AsyncSession, organisation_id: uuid.UUID, user_id: uuid.UUID
) -> OrganisationMember | None:
    member: OrganisationMember | None = await session.scalar(
        select(OrganisationMember).where(
            OrganisationMember.organisation_id == organisation_id,
            OrganisationMember.user_id == user_id,
        )
    )
    return member


def require_org(permission: Permission) -> Callable[..., Awaitable[OrgAccess]]:
    async def dependency(
        organisation_id: uuid.UUID,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> OrgAccess:
        org = await session.get(Organisation, organisation_id)
        if org is None:
            raise NotFoundError("Organisation not found")
        member = await get_membership(session, org.id, user.id)
        if member is None:
            if user.is_platform_admin and permission in PLATFORM_ADMIN_PERMISSIONS:
                return OrgAccess(user, org, None)
            # 404 rather than 403: do not confirm that a foreign organisation exists.
            raise NotFoundError("Organisation not found")
        if not org.is_active:
            raise NotFoundError("Organisation not found")
        if not role_has(member.role, permission):
            raise ForbiddenError("Your role does not permit this action")
        return OrgAccess(user, org, member.role)

    return dependency


def require_project(permission: Permission) -> Callable[..., Awaitable[ProjectAccess]]:
    async def dependency(
        project_id: uuid.UUID,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> ProjectAccess:
        project = await session.scalar(
            select(Project).where(Project.id == project_id, Project.deleted_at.is_(None))
        )
        if project is None:
            raise NotFoundError("Project not found")
        member = await get_membership(session, project.organisation_id, user.id)
        org = await session.get(Organisation, project.organisation_id)
        if member is None or org is None or not org.is_active:
            raise NotFoundError("Project not found")
        if not role_has(member.role, permission):
            raise ForbiddenError("Your role does not permit this action")
        return ProjectAccess(user, project, member.role)

    return dependency


def require_crawl(permission: Permission) -> Callable[..., Awaitable[CrawlAccess]]:
    async def dependency(
        crawl_id: uuid.UUID,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> CrawlAccess:
        crawl = await session.get(CrawlJob, crawl_id)
        if crawl is None:
            raise NotFoundError("Crawl not found")
        project = await session.scalar(
            select(Project).where(
                Project.id == crawl.project_id,
                Project.organisation_id == crawl.organisation_id,
                Project.deleted_at.is_(None),
            )
        )
        member = await get_membership(session, crawl.organisation_id, user.id)
        org = await session.get(Organisation, crawl.organisation_id)
        if project is None or member is None or org is None or not org.is_active:
            raise NotFoundError("Crawl not found")
        if not role_has(member.role, permission):
            raise ForbiddenError("Your role does not permit this action")
        return CrawlAccess(user, crawl, project, member.role)

    return dependency


def require_issue(permission: Permission) -> Callable[..., Awaitable[IssueAccess]]:
    async def dependency(
        issue_id: uuid.UUID,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> IssueAccess:
        issue = await session.get(SeoIssue, issue_id)
        if issue is None:
            raise NotFoundError("Issue not found")
        project = await session.scalar(
            select(Project).where(
                Project.id == issue.project_id,
                Project.organisation_id == issue.organisation_id,
                Project.deleted_at.is_(None),
            )
        )
        member = await get_membership(session, issue.organisation_id, user.id)
        org = await session.get(Organisation, issue.organisation_id)
        if project is None or member is None or org is None or not org.is_active:
            raise NotFoundError("Issue not found")
        if not role_has(member.role, permission):
            raise ForbiddenError("Your role does not permit this action")
        return IssueAccess(user, issue, project, member.role)

    return dependency
