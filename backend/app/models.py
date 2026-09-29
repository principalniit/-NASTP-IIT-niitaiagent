"""Import every model so SQLAlchemy metadata and Alembic see the full schema."""

from app.modules.audit_logs.models import AuditLog
from app.modules.auth.models import RefreshToken
from app.modules.crawler.models import CrawlJob, CrawlLink, CrawlPage
from app.modules.organisations.models import Organisation, OrganisationMember, OrgRole
from app.modules.projects.models import Project, ProjectSettings
from app.modules.seo.models import InternalLinkRecommendation, SchemaFinding, SeoIssue, SeoScore
from app.modules.users.models import User

__all__ = [
    "AuditLog",
    "CrawlJob",
    "CrawlLink",
    "CrawlPage",
    "InternalLinkRecommendation",
    "OrgRole",
    "Organisation",
    "OrganisationMember",
    "Project",
    "ProjectSettings",
    "RefreshToken",
    "SchemaFinding",
    "SeoIssue",
    "SeoScore",
    "User",
]
