"""Import every model so SQLAlchemy metadata and Alembic see the full schema."""

from app.modules.audit_logs.models import AuditLog
from app.modules.auth.models import RefreshToken
from app.modules.organisations.models import Organisation, OrganisationMember, OrgRole
from app.modules.projects.models import Project, ProjectSettings
from app.modules.users.models import User

__all__ = [
    "AuditLog",
    "OrgRole",
    "Organisation",
    "OrganisationMember",
    "Project",
    "ProjectSettings",
    "RefreshToken",
    "User",
]
