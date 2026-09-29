from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.pagination import Page, PageParams, page_params
from app.core.request_context import get_request_meta
from app.modules.drafts import service
from app.modules.drafts.models import ApprovalAction, DraftStatus
from app.modules.drafts.schemas import (
    ApprovalOut,
    DraftCreate,
    DraftDecision,
    DraftDetail,
    DraftEdit,
    DraftNote,
    DraftOut,
    DraftRejection,
    DraftRollback,
    DraftVersionOut,
)
from app.modules.organisations.dependencies import (
    DraftAccess,
    ProjectAccess,
    require_draft,
    require_project,
)
from app.modules.organisations.permissions import Permission

router = APIRouter(tags=["drafts"])
Session = Annotated[AsyncSession, Depends(get_session)]
Author = Annotated[DraftAccess, Depends(require_draft(Permission.DRAFTS_CREATE))]
Reviewer = Annotated[DraftAccess, Depends(require_draft(Permission.APPROVALS_DECIDE))]


async def _detail(session: AsyncSession, access: DraftAccess) -> DraftDetail:
    versions, trail, people = await service.history(session, access.draft)
    return DraftDetail(
        **DraftOut.model_validate(access.draft).model_dump(),
        versions=[DraftVersionOut.model_validate(v) for v in versions],
        trail=[ApprovalOut.model_validate(a) for a in trail],
        people=people,
    )


@router.get("/projects/{project_id}/drafts", response_model=Page[DraftOut])
async def list_drafts(
    session: Session,
    paging: Annotated[PageParams, Depends(page_params)],
    access: Annotated[ProjectAccess, Depends(require_project(Permission.PROJECTS_READ))],
    status_filter: DraftStatus | None = None,
) -> Page[DraftOut]:
    items, total = await service.list_drafts(session, access.project, paging, status_filter)
    return Page(
        items=[DraftOut.model_validate(d) for d in items],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.post(
    "/projects/{project_id}/drafts", response_model=DraftOut, status_code=status.HTTP_201_CREATED
)
async def create_draft(
    body: DraftCreate,
    request: Request,
    session: Session,
    access: Annotated[ProjectAccess, Depends(require_project(Permission.DRAFTS_CREATE))],
) -> DraftOut:
    draft = await service.create(
        session, access.project, access.user, body, get_request_meta(request)
    )
    return DraftOut.model_validate(draft)


@router.get("/drafts/{draft_id}", response_model=DraftDetail)
async def get_draft(
    session: Session,
    access: Annotated[DraftAccess, Depends(require_draft(Permission.PROJECTS_READ))],
) -> DraftDetail:
    return await _detail(session, access)


@router.patch("/drafts/{draft_id}", response_model=DraftDetail)
async def edit_draft(
    body: DraftEdit, request: Request, session: Session, access: Author
) -> DraftDetail:
    await service.edit(
        session,
        access.draft,
        access.user,
        body.proposed_content,
        body.reason,
        get_request_meta(request),
    )
    return await _detail(session, access)


async def _act(
    session: AsyncSession,
    access: DraftAccess,
    request: Request,
    action: ApprovalAction,
    comment: str | None = None,
    source_reference: str | None = None,
) -> DraftDetail:
    await service.transition(
        session,
        access.draft,
        access.user,
        action,
        get_request_meta(request),
        comment,
        source_reference,
    )
    return await _detail(session, access)


@router.post("/drafts/{draft_id}/submit", response_model=DraftDetail)
async def submit(
    request: Request, session: Session, access: Author, body: DraftNote | None = None
) -> DraftDetail:
    return await _act(
        session, access, request, ApprovalAction.SUBMITTED, body.comment if body else None
    )


@router.post("/drafts/{draft_id}/approve", response_model=DraftDetail)
async def approve(
    body: DraftDecision, request: Request, session: Session, access: Reviewer
) -> DraftDetail:
    return await _act(
        session, access, request, ApprovalAction.APPROVED, body.comment, body.source_reference
    )


@router.post("/drafts/{draft_id}/reject", response_model=DraftDetail)
async def reject(
    body: DraftRejection, request: Request, session: Session, access: Reviewer
) -> DraftDetail:
    return await _act(session, access, request, ApprovalAction.REJECTED, body.comment)


@router.post("/drafts/{draft_id}/reopen", response_model=DraftDetail)
async def reopen(
    request: Request, session: Session, access: Author, body: DraftNote | None = None
) -> DraftDetail:
    return await _act(
        session, access, request, ApprovalAction.REOPENED, body.comment if body else None
    )


@router.post("/drafts/{draft_id}/mark-published", response_model=DraftDetail)
async def mark_published(
    request: Request, session: Session, access: Reviewer, body: DraftNote | None = None
) -> DraftDetail:
    return await _act(
        session, access, request, ApprovalAction.PUBLISHED, body.comment if body else None
    )


@router.post("/drafts/{draft_id}/rollback", response_model=DraftDetail)
async def rollback(
    body: DraftRollback, request: Request, session: Session, access: Reviewer
) -> DraftDetail:
    return await _act(session, access, request, ApprovalAction.ROLLED_BACK, body.comment)
