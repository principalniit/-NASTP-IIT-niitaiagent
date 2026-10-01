from fastapi import APIRouter

from app.api.health import router as health_router
from app.modules.ai.router import router as ai_router
from app.modules.audit_logs.router import router as audit_router
from app.modules.auth.router import router as auth_router
from app.modules.crawler.router import router as crawler_router
from app.modules.drafts.router import router as drafts_router
from app.modules.integrations.router import router as integrations_router
from app.modules.invitations.router import router as invitations_router
from app.modules.monitoring.router import router as monitoring_router
from app.modules.organisations.router import router as organisations_router
from app.modules.plans.router import router as plans_router
from app.modules.projects.router import router as projects_router
from app.modules.reports.router import router as reports_router
from app.modules.seo.router import router as seo_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(organisations_router)
api_router.include_router(invitations_router)
api_router.include_router(projects_router)
api_router.include_router(crawler_router)
api_router.include_router(seo_router)
api_router.include_router(ai_router)
api_router.include_router(drafts_router)
api_router.include_router(reports_router)
api_router.include_router(monitoring_router)
api_router.include_router(plans_router)
api_router.include_router(integrations_router)
api_router.include_router(audit_router)
