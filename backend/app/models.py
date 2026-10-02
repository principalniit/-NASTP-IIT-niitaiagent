"""Import every model so SQLAlchemy metadata and Alembic see the full schema."""

from app.modules.ai.models import AIAnalysis, AIFeedback, SeoRecommendation
from app.modules.audit_logs.models import AuditLog
from app.modules.auth.models import PasswordResetToken, RefreshToken
from app.modules.crawler.models import CrawlJob, CrawlLink, CrawlPage
from app.modules.drafts.models import Approval, ContentDraft, ContentDraftVersion
from app.modules.integrations.models import Integration
from app.modules.invitations.models import Invitation
from app.modules.monitoring.models import CrawlSchedule
from app.modules.organisations.models import Organisation, OrganisationMember, OrgRole
from app.modules.plans.models import Plan
from app.modules.projects.models import Project, ProjectSettings
from app.modules.reports.models import Report
from app.modules.search_data.models import SearchPageDay, SearchPageQuery, SearchSync
from app.modules.seo.models import InternalLinkRecommendation, SchemaFinding, SeoIssue, SeoScore
from app.modules.users.models import User

__all__ = [
    "AIAnalysis",
    "AIFeedback",
    "Approval",
    "AuditLog",
    "ContentDraft",
    "ContentDraftVersion",
    "CrawlJob",
    "CrawlLink",
    "CrawlPage",
    "CrawlSchedule",
    "Integration",
    "InternalLinkRecommendation",
    "Invitation",
    "OrgRole",
    "Organisation",
    "OrganisationMember",
    "PasswordResetToken",
    "Plan",
    "Project",
    "ProjectSettings",
    "RefreshToken",
    "Report",
    "SchemaFinding",
    "SearchPageDay",
    "SearchPageQuery",
    "SearchSync",
    "SeoIssue",
    "SeoRecommendation",
    "SeoScore",
    "User",
]
