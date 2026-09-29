from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.modules.users.models import User


def normalise_email(email: str) -> str:
    return email.strip().lower()


async def get_by_email(session: AsyncSession, email: str) -> User | None:
    user: User | None = await session.scalar(
        select(User).where(User.email == normalise_email(email))
    )
    return user


def build_user(email: str, full_name: str, password: str, *, platform_admin: bool = False) -> User:
    return User(
        email=normalise_email(email),
        full_name=full_name.strip(),
        password_hash=hash_password(password),
        is_platform_admin=platform_admin,
    )
