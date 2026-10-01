"""Measuring the AI assistant.

Two tools, both run by an operator from the command line:

- `usage_report` summarises the AI tasks an organisation has already run: how many
  succeeded, how long they took, how large the prompts were, how often the model had to
  be loaded, and why tasks failed.
- `run_cases` runs a fixed test set through the same code path as real tasks and scores
  each answer. Every case runs inside a transaction that is rolled back, so an evaluation
  leaves nothing behind: no tasks, recommendations or drafts, and no usage counted.

The scores are checks on real answers, not estimates: whether the task completed,
whether it passed the grounding check, and whether it cited the issues it should have.
"""

import json
import re
import time
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.ai.models import AIAnalysis, AIKind, AIStatus
from app.modules.ai.provider import AIError
from app.modules.ai.runner import _execute, _fail
from app.modules.ai.tools import IssuesArgs, ToolContext, ToolError, get_seo_issues
from app.modules.projects.models import Project
from app.modules.seo.models import ResolutionStatus, SeoIssue

DEFAULT_CASES = Path(__file__).with_name("eval_cases.json")
# A model load longer than this means the model was not in memory when the task began.
LOAD_THRESHOLD_MS = 1000
TOP_ISSUES = 5
# Wording that says the platform has no data for the question. Deliberately broad: the
# check only confirms the answer admits the gap instead of inventing figures, and the
# grounding check separately rejects numbers that are not in the data.
_MISSING_DATA = re.compile(
    r"\b(not available|unavailable|no data|does not (have|include|contain)|"
    r"do(es)? not track|doesn't (have|include|contain)|not (tracked|measured|collected)|"
    r"no information|cannot (tell|answer|say|determine)|not part of)\b",
    re.I,
)


# ---------------------------------------------------------------------------------------
# Report on past tasks


@dataclass
class KindStats:
    kind: str
    total: int
    completed: int
    failed: int
    avg_attempts: float | None
    median_seconds: float | None
    avg_prompt_tokens: int | None
    cold_starts: int  # tasks that waited for the model to load


@dataclass
class UsageReport:
    since: datetime
    kinds: list[KindStats]
    failure_reasons: list[tuple[str, int]]
    models: list[tuple[str, int]]


def _tries(analysis: AIAnalysis) -> int:
    """Model calls the task made. The provider's count includes calls of tasks that failed
    on invalid replies, which never get as far as recording their attempts."""
    calls = (analysis.metrics or {}).get("calls")
    return int(calls) if calls else analysis.attempts


def _reason(analysis: AIAnalysis) -> list[str]:
    """Why a task failed, grouped so that similar failures count together."""
    violations = (analysis.grounding or {}).get("violations") or []
    if violations:
        # "Uses numbers that are not in the project data: 42, 7" -> the part before ":",
        # except for claim types, whose description is the useful part.
        return [
            v if v.startswith("Makes an unsupported claim") else v.split(":")[0] for v in violations
        ]
    text = analysis.error or "Unknown error"
    return [re.sub(r"\s*\(.*\)\.?$", "", text).strip()]


async def usage_report(session: AsyncSession, org_id: uuid.UUID, since: datetime) -> UsageReport:
    rows = list(
        await session.scalars(
            select(AIAnalysis)
            .where(
                AIAnalysis.organisation_id == org_id,
                AIAnalysis.created_at >= since,
                AIAnalysis.status.in_([AIStatus.COMPLETED, AIStatus.FAILED]),
            )
            .order_by(AIAnalysis.created_at.desc())
            .limit(5000)
        )
    )
    kinds: list[KindStats] = []
    for kind in AIKind:
        group = [r for r in rows if r.kind == kind]
        if not group:
            continue
        metrics = [r.metrics for r in group if r.metrics]
        seconds = [r.duration_ms / 1000 for r in group if r.duration_ms is not None]
        kinds.append(
            KindStats(
                kind=kind.value,
                total=len(group),
                completed=sum(r.status == AIStatus.COMPLETED for r in group),
                failed=sum(r.status == AIStatus.FAILED for r in group),
                avg_attempts=round(mean(_tries(r) for r in group), 2),
                median_seconds=round(median(seconds), 1) if seconds else None,
                avg_prompt_tokens=(
                    round(
                        mean(m.get("prompt_tokens", 0) / max(m.get("calls", 1), 1) for m in metrics)
                    )
                    if metrics
                    else None
                ),
                cold_starts=sum(m.get("load_ms", 0) > LOAD_THRESHOLD_MS for m in metrics),
            )
        )
    reasons = Counter(reason for r in rows if r.status == AIStatus.FAILED for reason in _reason(r))
    models = Counter(r.model or "none" for r in rows)
    return UsageReport(
        since=since,
        kinds=kinds,
        failure_reasons=reasons.most_common(10),
        models=models.most_common(),
    )


# ---------------------------------------------------------------------------------------
# Test set


class Expect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Cites at least one of the highest-priority open issues.
    cites_top_issues: bool = False
    # Cites at least one open issue whose rule id starts with one of these, for example
    # "onpage.title". Skipped when the project has no such open issue.
    cites_rules: list[str] = Field(default_factory=list, max_length=20)
    # Says the platform has no data for this, instead of answering with invented figures.
    admits_missing_data: bool = False


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    kind: Literal["question", "management_summary", "issue_explanation"]
    # For questions only. The issue explained is always the highest-priority open issue.
    question: str | None = Field(default=None, min_length=3, max_length=1000)
    expect: Expect = Field(default_factory=Expect)

    @model_validator(mode="after")
    def _question_matches_kind(self) -> "EvalCase":
        if (self.kind == "question") != (self.question is not None):
            raise ValueError("'question' is required for questions and not allowed otherwise")
        return self


def load_cases(path: Path | None = None) -> list[EvalCase]:
    raw = json.loads((path or DEFAULT_CASES).read_text(encoding="utf-8"))
    cases = TypeAdapter(list[EvalCase]).validate_python(raw)
    names = [c.name for c in cases]
    if len(set(names)) != len(names):
        raise ValueError("Every case needs a unique name")
    return cases


@dataclass
class CaseResult:
    name: str
    kind: str
    passed: bool
    completed: bool
    grounded: bool
    seconds: float
    attempts: int
    prompt_tokens: int | None
    cold_start: bool
    problems: list[str] = field(default_factory=list)
    skipped_checks: list[str] = field(default_factory=list)
    # The answer itself, so people can judge its quality, and the titles of the issues it
    # cites in place of their ids.
    output: dict[str, Any] | None = None
    cited_issues: list[str] = field(default_factory=list)

    @property
    def preview(self) -> str:
        texts = _texts(self.output)
        text = " ".join(texts[0].split()) if texts else ""
        return text if len(text) <= 200 else text[:197] + "..."


def _cited(output: Any) -> set[str]:
    """Issue ids the answer relies on, from every `issue_ids` list in it."""
    found: set[str] = set()
    if isinstance(output, dict):
        for key, value in output.items():
            if key == "issue_ids" and isinstance(value, list):
                found |= {str(v) for v in value}
            else:
                found |= _cited(value)
    elif isinstance(output, list):
        for item in output:
            found |= _cited(item)
    return found


def _texts(output: Any) -> list[str]:
    if isinstance(output, dict):
        return [t for k, v in output.items() if k != "issue_ids" for t in _texts(v)]
    if isinstance(output, list):
        return [t for v in output for t in _texts(v)]
    return [output] if isinstance(output, str) else []


async def _titles(session: AsyncSession, project: Project, ids: set[str]) -> list[str]:
    valid = []
    for value in ids:
        try:
            valid.append(uuid.UUID(value))
        except ValueError:
            continue
    if not valid:
        return []
    rows = await session.execute(
        select(SeoIssue.title, SeoIssue.rule_id)
        .where(
            SeoIssue.id.in_(valid),
            SeoIssue.project_id == project.id,
            SeoIssue.organisation_id == project.organisation_id,
        )
        .order_by(SeoIssue.priority_score.desc())
    )
    return [f"{title} ({rule})" for title, rule in rows.all()]


async def _issues_matching(
    session: AsyncSession, project: Project, prefixes: list[str]
) -> set[str]:
    result = await session.execute(
        select(SeoIssue.id, SeoIssue.rule_id).where(
            SeoIssue.project_id == project.id,
            SeoIssue.organisation_id == project.organisation_id,
            SeoIssue.resolution_status == ResolutionStatus.OPEN,
        )
    )
    return {str(i) for i, rule in result.all() if any(rule.startswith(p) for p in prefixes)}


def _score(
    case: EvalCase,
    analysis: AIAnalysis,
    top_ids: set[str],
    rule_ids: set[str] | None,
) -> tuple[list[str], list[str]]:
    """(problems, skipped checks) for a finished task."""
    if analysis.status != AIStatus.COMPLETED:
        return [analysis.error or "The task did not complete"], []
    problems: list[str] = []
    skipped: list[str] = []
    cited = _cited(analysis.output)
    if case.expect.cites_top_issues and not cited & top_ids:
        problems.append(f"Cites none of the {TOP_ISSUES} highest-priority open issues")
    if case.expect.cites_rules:
        if not rule_ids:
            skipped.append("cites_rules: the project has no open issue for these rules")
        elif not cited & rule_ids:
            problems.append("Cites no issue for the rules " + ", ".join(case.expect.cites_rules))
    if case.expect.admits_missing_data and not any(
        _MISSING_DATA.search(t) for t in _texts(analysis.output)
    ):
        problems.append("Does not say that the platform has no data for this")
    return problems, skipped


async def run_case(
    factory: async_sessionmaker[AsyncSession],
    project_id: uuid.UUID,
    case: EvalCase,
    *,
    model: str | None = None,
) -> CaseResult:
    async with factory() as session:
        project = await session.get(Project, project_id)
        if project is None:
            raise LookupError("Project not found")
        tools = ToolContext(session, project)
        try:
            top = (await get_seo_issues(tools, IssuesArgs(limit=TOP_ISSUES)))["issues"]
        except ToolError:
            top = []
        top_ids = {i["id"] for i in top}
        rule_ids = (
            await _issues_matching(session, project, case.expect.cites_rules)
            if case.expect.cites_rules
            else None
        )
        subject_type, subject_id, params = "project", None, {}
        if case.kind == "question":
            subject_type, params = "question", {"question": case.question or ""}
        elif case.kind == "issue_explanation" and top:
            subject_type, subject_id = "issue", top[0]["id"]
        analysis = AIAnalysis(
            organisation_id=project.organisation_id,
            project_id=project.id,
            kind=AIKind(case.kind),
            status=AIStatus.RUNNING,
            subject_type=subject_type,
            subject_id=subject_id,
            params=params,
        )
        session.add(analysis)
        await session.flush()
        started = time.monotonic()
        if case.kind == "issue_explanation" and not top:
            _fail(analysis, "The project has no open issue to explain")
        else:
            try:
                await _execute(session, analysis, model=model)
            except (AIError, ToolError) as exc:
                _fail(analysis, str(exc))
        seconds = round(time.monotonic() - started, 1)
        problems, skipped = _score(case, analysis, top_ids, rule_ids)
        metrics = analysis.metrics or {}
        result = CaseResult(
            name=case.name,
            kind=case.kind,
            passed=not problems,
            completed=analysis.status == AIStatus.COMPLETED,
            grounded=bool((analysis.grounding or {}).get("passed")),
            seconds=seconds,
            attempts=_tries(analysis),
            prompt_tokens=metrics.get("prompt_tokens") if metrics else None,
            cold_start=metrics.get("load_ms", 0) > LOAD_THRESHOLD_MS,
            problems=problems,
            skipped_checks=skipped,
            output=analysis.output,
            cited_issues=await _titles(session, project, _cited(analysis.output)),
        )
        # Nothing the evaluation did is kept.
        await session.rollback()
        return result


def summary(results: list[CaseResult]) -> dict[str, Any]:
    done = [r for r in results if r.completed]
    return {
        "cases": len(results),
        "passed": sum(r.passed for r in results),
        "completed": len(done),
        "grounded": sum(r.grounded for r in results),
        "median_seconds": round(median(r.seconds for r in results), 1) if results else None,
        "avg_prompt_tokens": (
            round(mean(r.prompt_tokens for r in done if r.prompt_tokens))
            if any(r.prompt_tokens for r in done)
            else None
        ),
    }


def as_json(results: list[CaseResult], meta: dict[str, Any]) -> str:
    return json.dumps(
        {**meta, "summary": summary(results), "results": [asdict(r) for r in results]},
        indent=2,
        default=str,
    )
