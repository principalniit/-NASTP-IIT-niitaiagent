"""Administrative commands.

    uv run python -m app.cli create-admin --email you@example.org --name "Your Name"
    uv run python -m app.cli seed-niit --owner-email you@example.org
    uv run python -m app.cli reset-password --email you@example.org
    uv run python -m app.cli rotate-secrets
    uv run python -m app.cli add-projects --org niit --owner-email you@example.org --file sites.csv
    uv run python -m app.cli ai-report --org niit --days 30
    uv run python -m app.cli ai-eval --org niit --project "NIIT website" [--model qwen2.5:7b]

Passwords are read from the ADMIN_PASSWORD environment variable or prompted for; they are
never accepted as command-line arguments, which would leak into shell history.
"""

import argparse
import asyncio
import getpass
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

import app.models  # noqa: F401  (registers every model so foreign keys resolve)
from app.core.database import dispose_engine, get_session_factory
from app.core.security import hash_password
from app.modules.audit_logs import service as audit
from app.modules.auth.models import RefreshToken
from app.modules.organisations.models import Organisation, OrganisationMember, OrgRole
from app.modules.organisations.schemas import OrganisationSettings
from app.modules.projects.models import Project, ProjectSettings
from app.modules.projects.schemas import ContentType, ProjectSettingsData
from app.modules.users.service import build_user, get_by_email

# Facts supplied in the project brief only. Everything else is entered by authorised users.
NIIT_ORG = {
    "name": "NASTP Institute of Information Technology",
    "slug": "niit",
    "domain": "niit.edu.pk",
    "timezone": "Asia/Karachi",
    "language": "en",
}
NIIT_PROJECT = {"name": "NIIT website", "root_url": "https://niit.edu.pk/", "domain": "niit.edu.pk"}
# (key, label, recommended schema.org types). Types are suggestions an authorised user
# can change; URL patterns are left empty because they must match the real site.
NIIT_CONTENT_TYPES = [
    ("about", "About NIIT", ["EducationalOrganization"]),
    ("programmes", "Academic programmes", ["Course"]),
    ("admissions", "Admissions", []),
    ("faculty", "Faculty", ["Person"]),
    ("research", "Research", []),
    ("news_events", "News and events", ["Event"]),
    ("training", "Training courses", ["Course"]),
    ("student_resources", "Student resources", []),
    ("contact", "Contact information", []),
]


def _password() -> str:
    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Password (min 12 chars): ")
    if not 12 <= len(password) <= 128:
        sys.exit("Password must be between 12 and 128 characters")
    return password


async def _revoke_sessions(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


async def create_admin(email: str, name: str) -> None:
    async with get_session_factory()() as session:
        user = await get_by_email(session, email)
        if user is not None:
            # The account may have been created by someone else with a password they know,
            # so promotion always sets a new password and ends existing sessions.
            print(f"{email} already has an account. Set a new password to promote it.")
            user.password_hash = hash_password(_password())
            user.is_platform_admin = True
            await _revoke_sessions(session, user.id)
            action = "promoted existing user (password reset)"
        else:
            user = build_user(email, name, _password(), platform_admin=True)
            session.add(user)
            action = "created"
        await session.flush()
        audit.record(
            session,
            action="admin.platform_admin_granted",
            actor_id=None,
            target_type="user",
            target_id=user.id,
        )
        await session.commit()
        print(f"Platform administrator {action}: {user.email}")


async def seed_niit(owner_email: str) -> None:
    async with get_session_factory()() as session:
        owner = await get_by_email(session, owner_email)
        if owner is None:
            sys.exit(f"No user with email {owner_email}. Run create-admin first.")
        org = await session.scalar(
            select(Organisation).where(Organisation.slug == NIIT_ORG["slug"])
        )
        if org is None:
            org = Organisation(**NIIT_ORG, settings=OrganisationSettings().model_dump(mode="json"))
            session.add(org)
            await session.flush()
            print("Created organisation:", org.name)
        else:
            print("Organisation already exists:", org.name)
        member = await session.scalar(
            select(OrganisationMember).where(
                OrganisationMember.organisation_id == org.id,
                OrganisationMember.user_id == owner.id,
            )
        )
        if member is None:
            session.add(
                OrganisationMember(organisation_id=org.id, user_id=owner.id, role=OrgRole.OWNER)
            )
            print("Added owner:", owner.email)
        project = await session.scalar(
            select(Project).where(
                Project.organisation_id == org.id,
                Project.domain == NIIT_PROJECT["domain"],
                Project.deleted_at.is_(None),
            )
        )
        if project is None:
            project = Project(organisation_id=org.id, created_by_id=owner.id, **NIIT_PROJECT)
            session.add(project)
            await session.flush()
            settings = ProjectSettingsData(
                content_types=[
                    ContentType(key=k, label=label, recommended_schema_types=types)
                    for k, label, types in NIIT_CONTENT_TYPES
                ]
            )
            session.add(
                ProjectSettings(
                    project_id=project.id,
                    organisation_id=org.id,
                    settings=settings.model_dump(mode="json"),
                    updated_by_id=owner.id,
                )
            )
            audit.record(
                session,
                action="project.created",
                actor_id=owner.id,
                organisation_id=org.id,
                target_type="project",
                target_id=project.id,
                details={"source": "seed-niit"},
            )
            print("Created project:", project.name)
        else:
            print("Project already exists:", project.name)
        await session.commit()


async def reset_password(email: str) -> None:
    """Set a new password and sign the account out everywhere."""
    async with get_session_factory()() as session:
        user = await get_by_email(session, email)
        if user is None:
            sys.exit(f"No user with email {email}.")
        user.password_hash = hash_password(_password())
        await _revoke_sessions(session, user.id)
        audit.record(
            session,
            action="user.password_reset",
            actor_id=None,
            target_type="user",
            target_id=user.id,
            details={"via": "cli"},
        )
        await session.commit()
        print(f"Password reset for {user.email}. Existing sessions were signed out.")


async def rotate_secrets() -> None:
    """Re-encrypt every stored integration credential with the first configured key."""
    from sqlalchemy.orm import undefer

    from app.core import crypto
    from app.modules.integrations.models import Integration

    async with get_session_factory()() as session:
        rows = list(
            await session.scalars(
                select(Integration)
                .where(Integration.secret_hint.is_not(None))
                .options(undefer(Integration.secret))
            )
        )
        for integration in rows:
            if integration.secret is not None:
                integration.secret = crypto.rotate(integration.secret)
        audit.record(
            session,
            action="integration.secrets_rotated",
            actor_id=None,
            details={"count": len(rows)},
        )
        await session.commit()
        print(f"Re-encrypted {len(rows)} stored credentials with the newest key.")


def read_sites(path: str) -> list[tuple[str, str]]:
    """Lines of "Name, https://address". Blank lines and lines starting with # are skipped."""
    sites = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, sep, url = line.rpartition(",")
        if not sep or not name.strip() or not url.strip():
            sys.exit(f"Line {number}: expected 'Name, https://address', got: {line}")
        sites.append((name.strip(), url.strip()))
    return sites


async def add_projects(org_slug: str, owner_email: str, path: str) -> None:
    """Create a project per line, with the same checks and limits as the dashboard."""
    from pydantic import ValidationError

    from app.core.errors import AppError
    from app.core.request_context import RequestMeta
    from app.modules.organisations.dependencies import OrgAccess
    from app.modules.projects import service as projects
    from app.modules.projects.schemas import ProjectCreate

    sites = read_sites(path)
    meta = RequestMeta(ip=None, user_agent="app.cli add-projects")
    created = 0
    for name, url in sites:
        # A fresh session per site: a duplicate rolls its session back, which must not
        # affect the others.
        async with get_session_factory()() as session:
            org = await session.scalar(select(Organisation).where(Organisation.slug == org_slug))
            if org is None:
                sys.exit(f"No organisation with slug '{org_slug}'.")
            user = await get_by_email(session, owner_email)
            if user is None:
                sys.exit(f"No user with email {owner_email}.")
            member = await session.scalar(
                select(OrganisationMember).where(
                    OrganisationMember.organisation_id == org.id,
                    OrganisationMember.user_id == user.id,
                )
            )
            if member is None and not user.is_platform_admin:
                sys.exit(f"{owner_email} is not a member of {org.name}.")
            if member is not None and member.role not in (OrgRole.OWNER, OrgRole.ADMIN):
                sys.exit(f"{owner_email} must be an owner or administrator of {org.name}.")
            access = OrgAccess(user=user, organisation=org, role=member.role if member else None)
            try:
                project = await projects.create(
                    session, access, ProjectCreate(name=name, root_url=url), meta
                )
            except ValidationError as exc:
                print(f"Skipped {name}: {exc.errors()[0]['msg']}")
                continue
            except AppError as exc:
                print(f"Skipped {name}: {exc.message}")
                continue
            created += 1
            print(f"Created {project.name}: {project.root_url}")
    print(f"{created} of {len(sites)} projects created.")


async def _org_by_slug(session: AsyncSession, slug: str) -> Organisation:
    org = await session.scalar(select(Organisation).where(Organisation.slug == slug))
    if org is None:
        sys.exit(f"No organisation with slug '{slug}'.")
    return org


async def ai_report(org_slug: str, days: int) -> None:
    """How the organisation's AI tasks went: success, speed, prompt size, failure reasons."""
    from datetime import timedelta

    from app.modules.ai.evaluation import usage_report

    since = datetime.now(UTC) - timedelta(days=days)
    async with get_session_factory()() as session:
        org = await _org_by_slug(session, org_slug)
        report = await usage_report(session, org.id, since)
    print(f"AI tasks for {org.name} since {since:%Y-%m-%d} ({days} days)")
    if not report.kinds:
        print("No finished AI tasks in this period.")
        return
    print(
        f"\n{'Task':<20}{'Total':>7}{'Done':>7}{'Failed':>8}{'Tries':>7}"
        f"{'Median s':>10}{'Prompt tok':>12}{'Cold':>6}"
    )
    for k in report.kinds:
        print(
            f"{k.kind:<20}{k.total:>7}{k.completed:>7}{k.failed:>8}"
            f"{k.avg_attempts if k.avg_attempts is not None else '-':>7}"
            f"{k.median_seconds if k.median_seconds is not None else '-':>10}"
            f"{k.avg_prompt_tokens if k.avg_prompt_tokens is not None else '-':>12}"
            f"{k.cold_starts:>6}"
        )
    print("\nTries: model calls per task, including retries. Prompt tok: average per call.")
    print("Cold: tasks that waited for the model to load into memory.")
    print("\nModels: " + ", ".join(f"{m} ({n})" for m, n in report.models))
    if report.failure_reasons:
        print("\nMost common failure reasons:")
        for reason, count in report.failure_reasons:
            print(f"  {count:>4}  {reason}")


async def ai_eval(
    org_slug: str, project_ref: str, cases_file: str | None, model: str | None, out: str | None
) -> None:
    """Run the test set against one project. Nothing is saved to the database."""
    from app.modules.ai.evaluation import as_json, load_cases, run_case, summary
    from app.modules.ai.prompts import PROMPT_VERSION
    from app.modules.projects.models import Project

    try:
        cases = load_cases(Path(cases_file) if cases_file else None)
    except (OSError, ValueError) as exc:
        sys.exit(f"Could not read the test cases: {exc}")
    factory = get_session_factory()
    async with factory() as session:
        org = await _org_by_slug(session, org_slug)
        projects = list(
            await session.scalars(
                select(Project).where(
                    Project.organisation_id == org.id, Project.deleted_at.is_(None)
                )
            )
        )
    ref = project_ref.strip().lower()
    matches = [p for p in projects if ref in (p.name.lower(), p.domain.lower())]
    if len(matches) != 1:
        names = ", ".join(sorted(p.name for p in projects))
        sys.exit(f"No single project called '{project_ref}' in {org.name}. Projects: {names}")
    project = matches[0]
    from app.modules.seo.service import latest_analysed_crawl

    async with factory() as session:
        crawl = await latest_analysed_crawl(session, project.id, org.id)
    if crawl is None:
        sys.exit(
            f"{project.name} has not been crawled and analysed yet, so there is nothing to "
            "test the AI on. Start a crawl from the dashboard, wait for the analysis to "
            "finish, then run ai-eval again."
        )
    print(f"Evaluating {len(cases)} cases on {project.name} ({project.domain})")
    print("Each case runs like a real AI task; nothing is saved.\n")
    results = []
    for case in cases:
        result = await run_case(factory, project.id, case, model=model)
        results.append(result)
        mark = "PASS" if result.passed else "FAIL"
        cold = " (model loaded)" if result.cold_start else ""
        print(f"{mark}  {case.name:<28} {result.seconds:>6}s  tries {result.attempts}{cold}")
        for problem in result.problems:
            print(f"      - {problem}")
        for skipped in result.skipped_checks:
            print(f"      ~ skipped {skipped}")
        if result.preview:
            print(f"      > {result.preview}")
    totals = summary(results)
    print(
        f"\nPassed {totals['passed']} of {totals['cases']}; completed {totals['completed']}, "
        f"grounded {totals['grounded']}; median {totals['median_seconds']} s per case; "
        f"average prompt {totals['avg_prompt_tokens'] or '-'} tokens."
    )
    if out:
        meta = {
            "organisation": org.slug,
            "project": project.name,
            "model": model or "configured",
            "prompt_version": PROMPT_VERSION,
            "run_at": datetime.now(UTC).isoformat(),
        }
        await asyncio.to_thread(Path(out).write_text, as_json(results, meta), encoding="utf-8")
        print(f"Results, including every answer in full, saved to {out}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    p_admin = sub.add_parser("create-admin", help="Create or promote a platform administrator")
    p_admin.add_argument("--email", required=True)
    p_admin.add_argument("--name", required=True)
    p_seed = sub.add_parser("seed-niit", help="Create the NIIT organisation and project")
    p_seed.add_argument("--owner-email", required=True)
    p_reset = sub.add_parser("reset-password", help="Set a new password for an account")
    p_reset.add_argument("--email", required=True)
    sub.add_parser("rotate-secrets", help="Re-encrypt integration credentials with the newest key")
    p_add = sub.add_parser("add-projects", help="Create projects from a 'Name, address' list")
    p_add.add_argument("--org", required=True, help="Organisation slug, for example niit")
    p_add.add_argument("--owner-email", required=True, help="Owner or admin recorded as creator")
    p_add.add_argument("--file", required=True, help="Text file with one 'Name, address' per line")
    p_report = sub.add_parser("ai-report", help="Summarise how AI tasks went and why they failed")
    p_report.add_argument("--org", required=True, help="Organisation slug, for example niit")
    p_report.add_argument("--days", type=int, default=30, choices=range(1, 366), metavar="1-365")
    p_eval = sub.add_parser("ai-eval", help="Score the AI on a fixed test set (saves nothing)")
    p_eval.add_argument("--org", required=True, help="Organisation slug, for example niit")
    p_eval.add_argument("--project", required=True, help="Project name or domain")
    p_eval.add_argument("--cases", help="JSON file of test cases (default: the starter set)")
    p_eval.add_argument("--model", help="Ollama model to test instead of the configured one")
    p_eval.add_argument("--out", help="Also save the results as JSON, to compare runs")
    args = parser.parse_args()

    async def run() -> None:
        try:
            if args.command == "create-admin":
                await create_admin(args.email, args.name)
            elif args.command == "reset-password":
                await reset_password(args.email)
            elif args.command == "rotate-secrets":
                await rotate_secrets()
            elif args.command == "add-projects":
                await add_projects(args.org, args.owner_email, args.file)
            elif args.command == "ai-report":
                await ai_report(args.org, args.days)
            elif args.command == "ai-eval":
                await ai_eval(args.org, args.project, args.cases, args.model, args.out)
            else:
                await seed_niit(args.owner_email)
        finally:
            await dispose_engine()

    asyncio.run(run())


if __name__ == "__main__":
    main()
