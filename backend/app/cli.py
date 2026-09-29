"""Administrative commands.

    uv run python -m app.cli create-admin --email you@example.org --name "Your Name"
    uv run python -m app.cli seed-niit --owner-email you@example.org

Passwords are read from the ADMIN_PASSWORD environment variable or prompted for; they are
never accepted as command-line arguments, which would leak into shell history.
"""

import argparse
import asyncio
import getpass
import os
import sys

from sqlalchemy import select

import app.models  # noqa: F401  (registers every model so foreign keys resolve)
from app.core.database import dispose_engine, get_session_factory
from app.modules.audit_logs import service as audit
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
NIIT_CONTENT_TYPES = [
    ("about", "About NIIT"),
    ("programmes", "Academic programmes"),
    ("admissions", "Admissions"),
    ("faculty", "Faculty"),
    ("research", "Research"),
    ("news_events", "News and events"),
    ("training", "Training courses"),
    ("student_resources", "Student resources"),
    ("contact", "Contact information"),
]


def _password() -> str:
    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Password (min 12 chars): ")
    if not 12 <= len(password) <= 128:
        sys.exit("Password must be between 12 and 128 characters")
    return password


async def create_admin(email: str, name: str) -> None:
    async with get_session_factory()() as session:
        user = await get_by_email(session, email)
        if user is not None:
            user.is_platform_admin = True
            action = "promoted existing user"
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
                content_types=[ContentType(key=k, label=label) for k, label in NIIT_CONTENT_TYPES]
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


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    p_admin = sub.add_parser("create-admin", help="Create or promote a platform administrator")
    p_admin.add_argument("--email", required=True)
    p_admin.add_argument("--name", required=True)
    p_seed = sub.add_parser("seed-niit", help="Create the NIIT organisation and project")
    p_seed.add_argument("--owner-email", required=True)
    args = parser.parse_args()

    async def run() -> None:
        try:
            if args.command == "create-admin":
                await create_admin(args.email, args.name)
            else:
                await seed_niit(args.owner_email)
        finally:
            await dispose_engine()

    asyncio.run(run())


if __name__ == "__main__":
    main()
