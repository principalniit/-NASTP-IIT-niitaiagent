"""Execute one queued AI analysis. Called by the worker; never inside a web request."""

import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import get_session_factory
from app.modules.ai.agent import answer_question
from app.modules.ai.grounding import check_output
from app.modules.ai.models import AIAnalysis, AIKind, AIStatus
from app.modules.ai.prompts import PROMPT_VERSION, system_prompt, user_prompt
from app.modules.ai.provider import AIError, build_provider, choose_provider
from app.modules.ai.refs import IssueRefs
from app.modules.ai.tasks import TASKS, TaskEnv, issue_ids_in
from app.modules.ai.tools import ToolContext, ToolError
from app.modules.organisations.models import Organisation
from app.modules.organisations.schemas import OrganisationSettings
from app.modules.projects.models import Project
from app.modules.projects.schemas import ProjectSettingsData
from app.modules.projects.service import get_settings_row
from app.modules.users.models import User

logger = logging.getLogger(__name__)


def json_safe(value: Any) -> Any:
    """Evidence as plain JSON, so it can be stored. Tool results can hold datetimes (for
    example the crawl comparison), which the database's JSON column cannot encode."""
    return json.loads(json.dumps(value, default=str))


def _fail(analysis: AIAnalysis, message: str) -> None:
    analysis.status = AIStatus.FAILED
    analysis.error = message


async def run_analysis(
    analysis_id: uuid.UUID, *, factory: async_sessionmaker[AsyncSession] | None = None
) -> AIStatus:
    factory = factory or get_session_factory()
    async with factory() as session:
        analysis = await session.get(AIAnalysis, analysis_id)
        if analysis is None:
            raise LookupError(f"AI analysis {analysis_id} not found")
        started = time.monotonic()
        analysis.started_at = analysis.started_at or datetime.now(UTC)
        try:
            await _execute(session, analysis)
        except (AIError, ToolError) as exc:
            _fail(analysis, str(exc))
        analysis.duration_ms = int((time.monotonic() - started) * 1000)
        analysis.finished_at = datetime.now(UTC)
        await session.commit()
        logger.info(
            "AI analysis finished",
            extra={
                "ai_analysis_id": str(analysis.id),
                "kind": analysis.kind.value,
                "status": analysis.status.value,
                "attempts": analysis.attempts,
            },
        )
        return analysis.status


async def _execute(session: AsyncSession, analysis: AIAnalysis) -> None:
    project = await session.get(Project, analysis.project_id)
    org = await session.get(Organisation, analysis.organisation_id)
    if project is None or org is None or project.deleted_at is not None:
        raise AIError("The project no longer exists.")
    org_settings = OrganisationSettings.model_validate(org.settings)
    choice = choose_provider(org_settings)
    analysis.provider, analysis.model, analysis.prompt_version = (
        choice.provider,
        choice.model,
        PROMPT_VERSION,
    )
    if not choice.enabled or choice.model is None:
        raise AIError(choice.reason or "AI is not available.")
    provider = build_provider(choice)
    tools = ToolContext(session, project)
    system = system_prompt(org.name, org_settings, org.language)
    requester = (
        await session.get(User, analysis.requested_by_id) if analysis.requested_by_id else None
    )

    if analysis.kind == AIKind.QUESTION:
        answer, evidence, report, attempts = await answer_question(
            provider, tools, system, str(analysis.params.get("question", ""))
        )
        analysis.evidence, analysis.attempts = json_safe(evidence), attempts
        analysis.output = answer.model_dump(mode="json") if report.passed else None
        analysis.grounding = report.as_dict()
        if not report.passed:
            _fail(analysis, "The answer included claims not supported by the project data.")
            return
        analysis.status = AIStatus.COMPLETED
        return

    plan_fn, finish_fn = TASKS[analysis.kind]
    env = TaskEnv(
        session=session,
        tools=tools,
        analysis=analysis,
        org_settings=org_settings,
        project_settings=ProjectSettingsData.model_validate(
            (await get_settings_row(session, project)).settings
        ),
        requester=requester,
    )
    plan = await plan_fn(env)
    analysis.evidence = json_safe(plan.evidence)
    analysis.crawl_job_id = plan.crawl_id or analysis.crawl_job_id
    known = issue_ids_in(plan.evidence)
    refs = IssueRefs()  # the model sees short issue references, mapped back below
    messages = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": user_prompt(plan.task, refs.shorten(plan.evidence), plan.schema),
        },
    ]
    output, attempts, raw = await provider.chat_structured(messages, plan.schema)
    output = refs.expand(output)
    report = check_output(output, plan.evidence, known)
    if not report.passed:
        messages += [
            {"role": "assistant", "content": raw[:6000]},
            {
                "role": "user",
                "content": (
                    "Your reply is not grounded in the evidence: "
                    + "; ".join(report.violations)
                    + ". Reply again using only facts, numbers and issue references (such as "
                    "issue-a) that appear in the evidence."
                ),
            },
        ]
        output, more, raw = await provider.chat_structured(messages, plan.schema)
        output = refs.expand(output)
        attempts += more
        report = check_output(output, plan.evidence, known)
    analysis.attempts = attempts
    # Output that failed grounding is never stored, so no screen or API can show it.
    analysis.output = output.model_dump(mode="json") if report.passed else None
    analysis.grounding = report.as_dict()
    if not report.passed:
        _fail(
            analysis,
            "The AI reply included claims not supported by the project data, so it was not used.",
        )
        return
    await finish_fn(env, plan, output)
    analysis.status = AIStatus.COMPLETED


def evidence_size(analysis: AIAnalysis) -> int:
    return len(json.dumps(analysis.evidence, default=str))
