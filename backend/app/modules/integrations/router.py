from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.core.database import get_session
from app.core.request_context import get_request_meta
from app.modules.auth.dependencies import CurrentUser
from app.modules.integrations import service
from app.modules.integrations.schemas import (
    IntegrationCreate,
    IntegrationOut,
    IntegrationUpdate,
    ProviderOut,
)
from app.modules.organisations.dependencies import (
    IntegrationAccess,
    OrgAccess,
    require_integration,
    require_org,
)
from app.modules.organisations.permissions import Permission

router = APIRouter(tags=["integrations"])
Session = Annotated[AsyncSession, Depends(get_session)]
Manage = Annotated[OrgAccess, Depends(require_org(Permission.ORG_UPDATE))]
ManageIntegration = Annotated[
    IntegrationAccess, Depends(require_integration(Permission.ORG_UPDATE))
]


@router.get("/integration-providers", response_model=list[ProviderOut])
async def providers(user: CurrentUser) -> list[ProviderOut]:
    return service.providers()


@router.get("/organisations/{organisation_id}/integrations", response_model=list[IntegrationOut])
async def list_integrations(session: Session, access: Manage) -> list[IntegrationOut]:
    return await service.list_integrations(session, access)


@router.get("/organisations/{organisation_id}/integrations/encryption")
async def encryption_status(access: Manage) -> dict[str, bool]:
    return {"available": crypto.available()}


@router.post(
    "/organisations/{organisation_id}/integrations",
    response_model=IntegrationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_integration(
    body: IntegrationCreate, request: Request, session: Session, access: Manage
) -> IntegrationOut:
    return await service.create(session, access, body, get_request_meta(request))


@router.patch("/integrations/{integration_id}", response_model=IntegrationOut)
async def update_integration(
    body: IntegrationUpdate, request: Request, session: Session, access: ManageIntegration
) -> IntegrationOut:
    return await service.update(session, access, body, get_request_meta(request))


@router.delete("/integrations/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_integration(request: Request, session: Session, access: ManageIntegration) -> None:
    await service.delete(session, access, get_request_meta(request))
