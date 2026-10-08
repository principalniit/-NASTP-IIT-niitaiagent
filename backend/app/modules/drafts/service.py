"""Draft lifecycle. Every transition is checked here and recorded in the approval trail.

draft          --submit-->          pending_review
pending_review --approve/reject-->  approved | rejected
approved       --mark published-->  published      (recorded only; nothing is published)
published      --roll back-->       rolled_back    (recorded only)
approved, rejected --reopen-->      draft
draft, rejected --edit-->           draft (new version)

Separation of duties: nobody who created the draft, requested it from the AI assistant, wrote
any of its versions, or submitted the current version can approve it. AI drafts have no human
author, so the person who submits one is treated as its sponsor.

Protected-fact detection compares the proposal with the value the crawler recorded, never
with an "original" typed in by the author, which could already contain the new facts.
"""

import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    AppError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationAppError,
)
from app.core.pagination import PageParams
from app.core.request_context import RequestMeta
from app.modules.ai.models import AIAnalysis
from app.modules.audit_logs import service as audit
from app.modules.crawler.models import CrawlPage
from app.modules.crawler.urls import normalise_url
from app.modules.drafts.models import (
    Approval,
    ApprovalAction,
    ContentDraft,
    ContentDraftVersion,
    DraftField,
    DraftSource,
    DraftStatus,
)
from app.modules.drafts.protected import protected_reasons
from app.modules.drafts.schemas import DraftCreate
from app.modules.projects.models import Project, ProjectSettings
from app.modules.projects.schemas import ProjectSettingsData
from app.modules.seo.models import SeoIssue
from app.modules.seo.service import latest_analysed_crawl
from app.modules.users.models import User

EDITABLE = (DraftStatus.DRAFT, DraftStatus.REJECTED)


def _now() -> datetime:
    return datetime.now(UTC)


def _trail(
    session: AsyncSession,
    draft: ContentDraft,
    action: ApprovalAction,
    actor: User | None,
    from_status: DraftStatus | None,
    comment: str | None = None,
    source_reference: str | None = None,
) -> None:
    session.add(
        Approval(
            organisation_id=draft.organisation_id,
            draft_id=draft.id,
            version=draft.version,
            action=action,
            from_status=from_status.value if from_status else None,
            to_status=draft.status.value,
            actor_id=actor.id if actor else None,
            comment=comment,
            source_reference=source_reference,
        )
    )


def _audit(
    session: AsyncSession,
    draft: ContentDraft,
    action: str,
    actor: User | None,
    meta: RequestMeta | None,
) -> None:
    audit.record(
        session,
        action=f"draft.{action}",
        actor_id=actor.id if actor else None,
        meta=meta,
        organisation_id=draft.organisation_id,
        target_type="content_draft",
        target_id=draft.id,
        details={
            "status": draft.status.value,
            "version": draft.version,
            "field": draft.field.value,
        },
    )


async def new_draft(
    session: AsyncSession,
    *,
    project: Project,
    page_url: str,
    field: DraftField,
    original: str | None,
    proposed: str,
    reason: str,
    evidence: dict[str, Any],
    source: DraftSource,
    author: User | None,
    crawl_page_id: uuid.UUID | None = None,
    ai_analysis_id: uuid.UUID | None = None,
    original_from_crawl: bool = True,
) -> ContentDraft:
    evidence = {**evidence, "original_from_crawl": original_from_crawl}
    reasons = protected_reasons(original if original_from_crawl else None, proposed)
    draft = ContentDraft(
        id=uuid.uuid4(),
        organisation_id=project.organisation_id,
        project_id=project.id,
        page_url=page_url,
        crawl_page_id=crawl_page_id,
        field=field,
        original_content=original,
        proposed_content=proposed,
        reason=reason,
        evidence=evidence,
        source=source,
        ai_analysis_id=ai_analysis_id,
        status=DraftStatus.DRAFT,
        version=1,
        protected=bool(reasons),
        protected_reasons=reasons,
        created_by_id=author.id if author else None,
        version_author_id=author.id if author else None,
    )
    session.add(draft)
    await session.flush()  # the version and trail rows reference the draft
    session.add(
        ContentDraftVersion(
            organisation_id=draft.organisation_id,
            draft_id=draft.id,
            version=1,
            proposed_content=proposed,
            reason=reason,
            source=source,
            edited_by_id=author.id if author else None,
        )
    )
    _trail(
        session,
        draft,
        ApprovalAction.CREATED,
        author,
        None,
        comment="Generated by the AI assistant" if source == DraftSource.AI else None,
    )
    return draft


def _project_url(project: Project, value: str) -> str:
    """Resolve a URL or path against the project and require it to be on the project's site."""
    url = normalise_url(value.strip(), project.root_url)
    host = (urlsplit(url).hostname or "") if url else ""
    domain = project.domain.lower()
    if not url or not (host == domain or host.endswith("." + domain)):
        raise ValidationAppError("The page address must be on this project's website")
    return url


_CRAWLED_FIELDS = (DraftField.TITLE, DraftField.META_DESCRIPTION, DraftField.H1)


async def _crawled_value(
    session: AsyncSession, project: Project, page_url: str, field: DraftField
) -> tuple[str | None, uuid.UUID | None]:
    """The page's current value as last crawled, and the crawled page's id, if known."""
    if field not in _CRAWLED_FIELDS:
        return None, None
    crawl = await latest_analysed_crawl(session, project.id, project.organisation_id)
    if crawl is None:
        return None, None
    page = await session.scalar(
        select(CrawlPage).where(
            CrawlPage.crawl_job_id == crawl.id,
            CrawlPage.organisation_id == project.organisation_id,
            CrawlPage.url == page_url,
        )
    )
    if page is None:
        return None, None
    if field == DraftField.TITLE:
        return page.title, page.id
    if field == DraftField.META_DESCRIPTION:
        return page.meta_description, page.id
    h1 = next((h["text"] for h in page.headings if h.get("level") == 1), None)
    return h1, page.id


def _baseline(draft: ContentDraft) -> str | None:
    """The text protected-fact detection compares against (see the module docstring)."""
    return draft.original_content if draft.evidence.get("original_from_crawl", True) else None


async def create(
    session: AsyncSession, project: Project, user: User, body: DraftCreate, meta: RequestMeta
) -> ContentDraft:
    page_url = _project_url(project, body.page_url)
    issue_ids = [str(i) for i in body.issue_ids]
    if issue_ids:
        found = set(
            str(i)
            for i in await session.scalars(
                select(SeoIssue.id).where(
                    SeoIssue.id.in_(body.issue_ids),
                    SeoIssue.project_id == project.id,
                    SeoIssue.organisation_id == project.organisation_id,
                )
            )
        )
        if found != set(issue_ids):
            raise ValidationAppError("Some issues do not belong to this project")
    crawled, crawl_page_id = await _crawled_value(session, project, page_url, body.field)
    draft = await new_draft(
        session,
        project=project,
        page_url=page_url,
        field=body.field,
        original=crawled if crawl_page_id else body.original_content,
        original_from_crawl=crawl_page_id is not None,
        crawl_page_id=crawl_page_id,
        proposed=body.proposed_content,
        reason=body.reason,
        evidence={"issue_ids": issue_ids},
        source=DraftSource.HUMAN,
        author=user,
    )
    _audit(session, draft, "created", user, meta)
    await session.commit()
    await session.refresh(draft)
    return draft


async def get(
    session: AsyncSession, draft_id: uuid.UUID, organisation_id: uuid.UUID
) -> ContentDraft:
    draft = await session.scalar(
        select(ContentDraft).where(
            ContentDraft.id == draft_id, ContentDraft.organisation_id == organisation_id
        )
    )
    if draft is None:
        raise NotFoundError("Draft not found")
    return draft


async def list_drafts(
    session: AsyncSession,
    project: Project,
    params: PageParams,
    status: DraftStatus | None,
    *,
    page_url: str | None = None,
) -> tuple[list[ContentDraft], int]:
    query = select(ContentDraft).where(
        ContentDraft.project_id == project.id,
        ContentDraft.organisation_id == project.organisation_id,
    )
    if status:
        query = query.where(ContentDraft.status == status)
    if page_url:
        query = query.where(ContentDraft.page_url == page_url)
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await session.scalars(
        query.order_by(ContentDraft.updated_at.desc()).offset(params.offset).limit(params.page_size)
    )
    return list(rows), total


async def history(
    session: AsyncSession, draft: ContentDraft
) -> tuple[list[ContentDraftVersion], list[Approval], dict[str, str]]:
    versions = list(
        await session.scalars(
            select(ContentDraftVersion)
            .where(ContentDraftVersion.draft_id == draft.id)
            .order_by(ContentDraftVersion.version)
        )
    )
    trail = list(
        await session.scalars(
            select(Approval)
            .where(Approval.draft_id == draft.id)
            .order_by(Approval.created_at, Approval.id)
        )
    )
    ids = (
        {v.edited_by_id for v in versions}
        | {a.actor_id for a in trail}
        | {draft.created_by_id, draft.version_author_id, draft.reviewed_by_id}
    )
    ids.discard(None)
    people = (
        {
            str(u.id): u.full_name
            for u in await session.scalars(select(User).where(User.id.in_(ids)))
        }
        if ids
        else {}
    )
    return versions, trail, people


async def contributors(session: AsyncSession, draft: ContentDraft) -> set[uuid.UUID]:
    """Everyone who created, requested or wrote the draft, or submitted the current version."""
    authors = await session.scalars(
        select(ContentDraftVersion.edited_by_id).where(ContentDraftVersion.draft_id == draft.id)
    )
    submitters = await session.scalars(
        select(Approval.actor_id).where(
            Approval.draft_id == draft.id,
            Approval.action == ApprovalAction.SUBMITTED,
            Approval.version == draft.version,
        )
    )
    people = {draft.created_by_id, draft.version_author_id, *authors, *submitters}
    if draft.ai_analysis_id is not None:
        # Whoever asked the assistant for this draft (and could steer it) is a contributor too.
        people.add(
            await session.scalar(
                select(AIAnalysis.requested_by_id).where(AIAnalysis.id == draft.ai_analysis_id)
            )
        )
    return {p for p in people if p is not None}


def _under(url: str, source: str) -> bool:
    ref, base = urlsplit(url), urlsplit(source)
    if (
        ref.scheme != "https"
        or (ref.hostname or "") != (base.hostname or "")
        or ref.port != base.port
    ):
        return False
    prefix = base.path.rstrip("/")
    return ref.path == prefix or ref.path.startswith(prefix + "/") or not prefix


async def _check_source(
    session: AsyncSession, draft: ContentDraft, source_reference: str | None
) -> str:
    """A protected draft needs a source. A web address must be on an approved source."""
    reference = (source_reference or "").strip()
    if not reference:
        raise ConflictError(
            "This draft changes official information. Approving it requires a verified source "
            "reference: a page on one of the project's approved sources, or an official document."
        )
    if "://" in reference or reference.lower().startswith("www."):
        row = await session.scalar(
            select(ProjectSettings).where(
                ProjectSettings.project_id == draft.project_id,
                ProjectSettings.organisation_id == draft.organisation_id,
            )
        )
        sources = (
            ProjectSettingsData.model_validate(row.settings).institutional_profile.approved_sources
            if row
            else []
        )
        if not any(_under(reference, str(s.url)) for s in sources):
            raise ConflictError(
                "That web address is not on one of the project's approved sources. Cite a page "
                "on an approved source, or an official document by name and reference number."
            )
    return reference


def _require(draft: ContentDraft, allowed: tuple[DraftStatus, ...], action: str) -> None:
    if draft.status not in allowed:
        raise ConflictError(
            f"A draft that is {draft.status.value.replace('_', ' ')} cannot be {action}"
        )


async def edit(
    session: AsyncSession,
    draft: ContentDraft,
    user: User,
    content: str,
    reason: str,
    meta: RequestMeta,
) -> ContentDraft:
    await session.refresh(draft, with_for_update=True)  # no concurrent review or edit
    _require(draft, EDITABLE, "edited")
    if content.strip() == draft.proposed_content.strip():
        raise ConflictError("The proposed content is unchanged")
    previous = draft.status
    draft.version += 1
    draft.proposed_content = content
    draft.reason = reason
    draft.version_author_id = user.id
    draft.status = DraftStatus.DRAFT
    reasons = protected_reasons(_baseline(draft), content)
    draft.protected, draft.protected_reasons = bool(reasons), reasons
    session.add(
        ContentDraftVersion(
            organisation_id=draft.organisation_id,
            draft_id=draft.id,
            version=draft.version,
            proposed_content=content,
            reason=reason,
            source=DraftSource.HUMAN,
            edited_by_id=user.id,
        )
    )
    _trail(session, draft, ApprovalAction.EDITED, user, previous)
    _audit(session, draft, "edited", user, meta)
    await session.commit()
    await session.refresh(draft)
    return draft


async def transition(
    session: AsyncSession,
    draft: ContentDraft,
    user: User,
    action: ApprovalAction,
    meta: RequestMeta,
    comment: str | None = None,
    source_reference: str | None = None,
) -> ContentDraft:
    await session.refresh(draft, with_for_update=True)  # no concurrent review or edit
    previous = draft.status
    if action == ApprovalAction.SUBMITTED:
        _require(draft, (DraftStatus.DRAFT,), "submitted for review")
        draft.status = DraftStatus.PENDING_REVIEW
    elif action == ApprovalAction.APPROVED:
        _require(draft, (DraftStatus.PENDING_REVIEW,), "approved")
        if user.id in await contributors(session, draft):
            raise ForbiddenError(
                "People who wrote or submitted this draft cannot approve it; another reviewer must"
            )
        if draft.protected:
            source_reference = await _check_source(session, draft, source_reference)
        draft.status = DraftStatus.APPROVED
        draft.reviewed_by_id = user.id
        draft.reviewed_at = _now()
        draft.source_reference = source_reference
    elif action == ApprovalAction.REJECTED:
        _require(draft, (DraftStatus.PENDING_REVIEW,), "rejected")
        draft.status = DraftStatus.REJECTED
        draft.reviewed_by_id = user.id
        draft.reviewed_at = _now()
    elif action == ApprovalAction.REOPENED:
        _require(draft, (DraftStatus.APPROVED, DraftStatus.REJECTED), "reopened")
        draft.status = DraftStatus.DRAFT
        draft.reviewed_by_id = None
        draft.reviewed_at = None
        draft.source_reference = None
    elif action == ApprovalAction.PUBLISHED:
        _require(draft, (DraftStatus.APPROVED,), "marked as published")
        draft.status = DraftStatus.PUBLISHED
        draft.published_at = _now()
    elif action == ApprovalAction.ROLLED_BACK:
        _require(draft, (DraftStatus.PUBLISHED,), "rolled back")
        draft.status = DraftStatus.ROLLED_BACK
        draft.rolled_back_at = _now()
    else:  # pragma: no cover - defensive
        raise AppError("Unsupported action")
    _trail(session, draft, action, user, previous, comment, source_reference)
    _audit(session, draft, action.value, user, meta)
    await session.commit()
    await session.refresh(draft)
    return draft
