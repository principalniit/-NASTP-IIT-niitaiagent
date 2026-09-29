"""Single source of truth for role-based permissions.

Routers declare the permission they need; nothing else decides access.
"""

import enum

from app.modules.organisations.models import OrgRole

OWN, ADM, MGR, EDT, VWR = (
    OrgRole.OWNER,
    OrgRole.ADMIN,
    OrgRole.SEO_MANAGER,
    OrgRole.EDITOR,
    OrgRole.VIEWER,
)


class Permission(enum.StrEnum):
    ORG_READ = "org:read"
    ORG_UPDATE = "org:update"
    MEMBERS_READ = "members:read"
    MEMBERS_MANAGE = "members:manage"
    AUDIT_READ = "audit:read"
    PROJECTS_READ = "projects:read"
    PROJECTS_CREATE = "projects:create"
    PROJECTS_UPDATE = "projects:update"
    PROJECTS_DELETE = "projects:delete"
    PROJECT_SETTINGS_UPDATE = "project_settings:update"
    # Declared now so the role matrix is fixed in one place; used from later phases.
    CRAWLS_START = "crawls:start"
    ISSUES_TRIAGE = "issues:triage"
    DRAFTS_CREATE = "drafts:create"
    APPROVALS_DECIDE = "approvals:decide"
    REPORTS_GENERATE = "reports:generate"


ROLE_PERMISSIONS: dict[Permission, frozenset[OrgRole]] = {
    Permission.ORG_READ: frozenset({OWN, ADM, MGR, EDT, VWR}),
    Permission.ORG_UPDATE: frozenset({OWN, ADM}),
    Permission.MEMBERS_READ: frozenset({OWN, ADM, MGR, EDT, VWR}),
    Permission.MEMBERS_MANAGE: frozenset({OWN, ADM}),
    Permission.AUDIT_READ: frozenset({OWN, ADM}),
    Permission.PROJECTS_READ: frozenset({OWN, ADM, MGR, EDT, VWR}),
    Permission.PROJECTS_CREATE: frozenset({OWN, ADM}),
    Permission.PROJECTS_UPDATE: frozenset({OWN, ADM, MGR}),
    Permission.PROJECTS_DELETE: frozenset({OWN, ADM}),
    Permission.PROJECT_SETTINGS_UPDATE: frozenset({OWN, ADM, MGR}),
    Permission.CRAWLS_START: frozenset({OWN, ADM, MGR}),
    Permission.ISSUES_TRIAGE: frozenset({OWN, ADM, MGR, EDT}),
    Permission.DRAFTS_CREATE: frozenset({OWN, ADM, MGR, EDT}),
    Permission.APPROVALS_DECIDE: frozenset({OWN, ADM, MGR}),
    Permission.REPORTS_GENERATE: frozenset({OWN, ADM, MGR}),
}

# Platform administrators may administer any organisation's profile and membership,
# but have no implicit access to its projects or SEO data. To support a tenant they
# add themselves as a member, which is audit-logged.
PLATFORM_ADMIN_PERMISSIONS = frozenset(
    {Permission.ORG_READ, Permission.ORG_UPDATE, Permission.MEMBERS_READ, Permission.MEMBERS_MANAGE}
)


def role_has(role: OrgRole, permission: Permission) -> bool:
    return role in ROLE_PERMISSIONS[permission]


def permissions_for(role: OrgRole) -> list[str]:
    return sorted(p.value for p, roles in ROLE_PERMISSIONS.items() if role in roles)
