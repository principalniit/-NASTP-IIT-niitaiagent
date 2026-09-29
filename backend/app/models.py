"""Import every model so SQLAlchemy metadata and Alembic see the full schema."""

from app.modules.ai.models import AIAnalysis, SeoRecommendation
from app.modules.audit_logs.models import AuditLog
from app.modules.auth.models import RefreshToken
from app.modules.crawler.models import CrawlJob, CrawlLink, CrawlPage
from app.modules.drafts.models import Approval, ContentDraft, ContentDraftVersion
from app.modules.monitoring.models import CrawlSchedule
from app.modules.organisations.models import Organisation, OrganisationMember, OrgRole
from app.modules.projects.models import Project, ProjectSettings
from app.modules.reports.models import Report
from app.modules.seo.models import InternalLinkRecommendation, SchemaFinding, SeoIssue, SeoScore
from app.modules.users.models import User

__all__ = [
    "AIAnalysis",
    "Approval",
    "AuditLog",
    "ContentDraft",
    "ContentDraftVersion",
    "CrawlJob",
    "CrawlLink",
    "CrawlPage",
    "CrawlSchedule",
    "InternalLinkRecommendation",
    "OrgRole",
    "Organisation",
    "OrganisationMember",
    "Project",
    "ProjectSettings",
    "RefreshToken",
    "Report",
    "SchemaFinding",
    "SeoIssue",
    "SeoRecommendation",
    "SeoScore",
    "User",
]
