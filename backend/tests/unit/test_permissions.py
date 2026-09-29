from itertools import pairwise

from app.modules.organisations.models import OrgRole
from app.modules.organisations.permissions import (
    PLATFORM_ADMIN_PERMISSIONS,
    ROLE_PERMISSIONS,
    Permission,
    permissions_for,
    role_has,
)


def test_every_permission_is_mapped() -> None:
    assert set(ROLE_PERMISSIONS) == set(Permission)


def test_owner_has_every_permission() -> None:
    assert all(role_has(OrgRole.OWNER, p) for p in Permission)


def test_viewer_is_read_only() -> None:
    allowed = set(permissions_for(OrgRole.VIEWER))
    assert allowed == {"org:read", "members:read", "projects:read"}


def test_editor_can_draft_but_not_approve_or_configure() -> None:
    assert role_has(OrgRole.EDITOR, Permission.DRAFTS_CREATE)
    assert not role_has(OrgRole.EDITOR, Permission.APPROVALS_DECIDE)
    assert not role_has(OrgRole.EDITOR, Permission.PROJECT_SETTINGS_UPDATE)


def test_roles_are_monotonic() -> None:
    order = [OrgRole.VIEWER, OrgRole.EDITOR, OrgRole.SEO_MANAGER, OrgRole.ADMIN, OrgRole.OWNER]
    for lower, higher in pairwise(order):
        assert set(permissions_for(lower)) <= set(permissions_for(higher))


def test_platform_admin_has_no_implicit_project_access() -> None:
    assert Permission.PROJECTS_READ not in PLATFORM_ADMIN_PERMISSIONS
