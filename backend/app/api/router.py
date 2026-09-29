from fastapi import APIRouter

from app.api.health import router as health_router
from app.modules.auth.router import router as auth_router
from app.modules.crawler.router import router as crawler_router
from app.modules.organisations.router import router as organisations_router
from app.modules.projects.router import router as projects_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(organisations_router)
api_router.include_router(projects_router)
api_router.include_router(crawler_router)
