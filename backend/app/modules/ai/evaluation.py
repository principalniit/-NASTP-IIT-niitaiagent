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

from app.modules.ai.models import AIAnalysis, AIFeedback, AIKind, AIStatus, FeedbackRating
from app.modules.ai.provider import AIError
from app.modules.ai.runner import _execute, _fail
from app.modules.ai.tools import IssuesArgs, ToolContext, ToolError, get_seo_issues
from app.modules.ai.topics import (
    ADMISSION_WITHIN_CHARS,
    MISSING_DATA,
    page_in,
    topics_in,
    unavailable_in,
)
from app.modules.crawler.urls import normalise_url
from app.modules.projects.models import Project
from app.modules.seo.models import ResolutionStatus, SeoIssue

DEFAULT_CASES = Path(__file__).with_name("eval_cases.json")
# A model load longer than this means the model was not in memory when the task began.
LOAD_THRESHOLD_MS = 1000
TOP_ISSUES = 5
# A reply that only says there is no answer. Checked on short answers only, so an answer
# that mentions a gap in passing still counts as an answer.
_REFUSAL = re.compile(
    r"(does not|doesn't) contain (an|any) answer|(has|have|is) no answer|"
    r"not available in the (project )?data|information is not available|"
    r"cannot (answer|tell)|no (relevant )?data (is )?available",
    re.I,
)
REFUSAL_MAX_CHARS = 200
# Saying that the latest crawl found none of what was asked about.
_NONE_FOUND = re.compile(
    r"\b(no|not any|none of the) (open |current )?([\w-]+ ){0,3}"
    r"(issues?|problems?|errors?|links?|pages?|images?|redirects?|headings?)\b|"
    r"\bnone (were|was) found|\b(did not|didn't|does not|doesn't) (find|show|report|have) any\b|"
    r"\bfound no\b",
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
class FeedbackSummary:
    helpful: int
    not_helpful: int
    reasons: list[tuple[str, int]]
    # (task kind, what was asked or produced, reason, comment), newest first.
    recent_complaints: list[tuple[str, str, str, str]]


@dataclass
class UsageReport:
    since: datetime
    kinds: list[KindStats]
    failure_reasons: list[tuple[str, int]]
    models: list[tuple[str, int]]
    feedback: FeedbackSummary


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
        feedback=await _feedback_summary(session, org_id, since),
    )


def _subject(analysis: AIAnalysis) -> str:
    if analysis.kind == AIKind.QUESTION:
        return str(analysis.params.get("question", ""))[:200]
    if analysis.kind in (AIKind.PAGE_PLAN, AIKind.METADATA_DRAFT, AIKind.CONTENT_OUTLINE):
        return str(analysis.params.get("page_url", ""))[:200]
    return analysis.kind.value.replace("_", " ")


async def _feedback_summary(
    session: AsyncSession, org_id: uuid.UUID, since: datetime
) -> FeedbackSummary:
    rows = (
        await session.execute(
            select(AIFeedback, AIAnalysis)
            .join(AIAnalysis, AIAnalysis.id == AIFeedback.ai_analysis_id)
            .where(
                AIFeedback.organisation_id == org_id,
                AIAnalysis.organisation_id == org_id,
                AIFeedback.updated_at >= since,
            )
            .order_by(AIFeedback.updated_at.desc())
            .limit(5000)
        )
    ).all()
    complaints = [(f, a) for f, a in rows if f.rating == FeedbackRating.NOT_HELPFUL]
    return FeedbackSummary(
        helpful=len(rows) - len(complaints),
        not_helpful=len(complaints),
        reasons=Counter(
            (f.reason.value if f.reason else "no reason given") for f, _ in complaints
        ).most_common(),
        recent_complaints=[
            (
                a.kind.value,
                _subject(a),
                f.reason.value if f.reason else "",
                f.comment or "",
            )
            for f, a in complaints[:10]
        ],
    )


async def feedback_cases(
    session: AsyncSession, org_id: uuid.UUID, since: datetime
) -> list[dict[str, Any]]:
    """Test cases from questions people marked not helpful, so real complaints are
    re-checked after every change. Expectations follow from the question's wording."""
    rows = (
        await session.execute(
            select(AIAnalysis)
            .join(AIFeedback, AIFeedback.ai_analysis_id == AIAnalysis.id)
            .where(
                AIFeedback.organisation_id == org_id,
                AIAnalysis.organisation_id == org_id,
                AIAnalysis.kind == AIKind.QUESTION,
                AIFeedback.rating == FeedbackRating.NOT_HELPFUL,
                AIFeedback.updated_at >= since,
            )
            .order_by(AIAnalysis.created_at.desc())
        )
    ).scalars()
    cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for analysis in rows:
        question = " ".join(str(analysis.params.get("question", "")).split())[:1000]
        if len(question) < 3 or question.lower() in seen:
            continue
        seen.add(question.lower())
        expect: dict[str, Any] = {}
        if unavailable_in(question):
            expect["admits_missing_data"] = True
        else:
            expect["answers"] = True
            prefixes = [p for t in topics_in(question) for p in t.rule_prefixes]
            if prefixes:
                expect["cites_rules"] = prefixes[:20]
            if page_in(question):
                expect["cites_page_issues"] = True
        cases.append(
            {
                "name": f"feedback-{analysis.created_at:%Y%m%d}-{str(analysis.id)[:8]}",
                "kind": "question",
                "question": question,
                "expect": expect,
            }
        )
    # Validated like any cases file, so the export can be run as it is.
    TypeAdapter(list[EvalCase]).validate_python(cases)
    return cases


# ---------------------------------------------------------------------------------------
# Test set


class Expect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Cites at least one of the highest-priority open issues.
    cites_top_issues: bool = False
    # Cites at least one open issue whose rule id starts with one of these, for example
    # "onpage.title". When the project has no such open issue, the answer must say that
    # none were found instead.
    cites_rules: list[str] = Field(default_factory=list, max_length=20)
    # Says the platform has no data for this, instead of answering with invented figures.
    admits_missing_data: bool = False
    # Gives a real answer, not only "the data has no answer". For questions the project
    # data always answers, such as priorities.
    answers: bool = False
    # For a question that names a page: cites at least one open issue on that page, or
    # says that none were found.
    cites_page_issues: bool = False

    @model_validator(mode="after")
    def _not_both(self) -> "Expect":
        if self.answers and self.admits_missing_data:
            raise ValueError("'answers' and 'admits_missing_data' contradict each other")
        return self


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
        if self.expect.cites_page_issues and not (self.question and page_in(self.question)):
            raise ValueError("'cites_page_issues' needs a question that names a page")
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


async def _issues_on_page(session: AsyncSession, project: Project, question: str) -> set[str]:
    url = page_in(question)
    if url is None:
        raise ValueError("cites_page_issues needs a question that names a page")
    target = normalise_url(url, project.root_url)
    rows = await session.scalars(
        select(SeoIssue.id).where(
            SeoIssue.project_id == project.id,
            SeoIssue.organisation_id == project.organisation_id,
            SeoIssue.resolution_status == ResolutionStatus.OPEN,
            SeoIssue.affected_urls.contains([target]),
        )
    )
    return {str(i) for i in rows}


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
    page_ids: set[str] | None = None,
) -> tuple[list[str], list[str]]:
    """(problems, skipped checks) for a finished task."""
    if analysis.status != AIStatus.COMPLETED:
        # The grounding check's own findings say what to fix; the error alone does not.
        violations = (analysis.grounding or {}).get("violations") or []
        return [analysis.error or "The task did not complete", *violations], []
    problems: list[str] = []
    skipped: list[str] = []
    cited = _cited(analysis.output)
    if case.expect.cites_top_issues and not cited & top_ids:
        problems.append(f"Cites none of the {TOP_ISSUES} highest-priority open issues")
    if case.expect.cites_rules:
        if not rule_ids:
            if not any(_NONE_FOUND.search(t) for t in _texts(analysis.output)):
                problems.append("Does not say that the latest crawl found none of these issues")
        elif not cited & rule_ids:
            problems.append("Cites no issue for the rules " + ", ".join(case.expect.cites_rules))
    if page_ids is not None:
        if not page_ids:
            if not any(_NONE_FOUND.search(t) for t in _texts(analysis.output)):
                problems.append("Does not say that the latest crawl found no issues on the page")
        elif not cited & page_ids:
            problems.append("Cites no open issue of the page the question names")
    if case.expect.answers:
        texts = _texts(analysis.output)
        main = texts[0].strip() if texts else ""
        if len(main) <= REFUSAL_MAX_CHARS and (not main or _REFUSAL.search(main)):
            problems.append("Says the data has no answer, although the project data has one")
    if case.expect.admits_missing_data:
        # Said up front, not after a list of unrelated issues.
        texts = _texts(analysis.output)
        opening = texts[0][:ADMISSION_WITHIN_CHARS] if texts else ""
        if not MISSING_DATA.search(opening):
            problems.append("Does not start by saying that the platform has no data for this")
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
        page_ids = (
            await _issues_on_page(session, project, case.question or "")
            if case.expect.cites_page_issues
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
        problems, skipped = _score(case, analysis, top_ids, rule_ids, page_ids)
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
