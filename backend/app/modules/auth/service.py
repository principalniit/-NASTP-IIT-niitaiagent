import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, NotFoundError, RateLimitedError, UnauthorizedError
from app.core.mailer import send_email
from app.core.rate_limit import FailureLimiter
from app.core.request_context import RequestMeta
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    password_needs_rehash,
    verify_password,
)
from app.modules.audit_logs import service as audit
from app.modules.auth.models import PasswordResetToken, RefreshToken
from app.modules.users.models import User
from app.modules.users.service import get_by_email, normalise_email

_settings = get_settings()
email_limiter = FailureLimiter(
    _settings.login_rate_limit_attempts, _settings.login_rate_limit_window_seconds
)
ip_limiter = FailureLimiter(
    _settings.login_rate_limit_ip_attempts, _settings.login_rate_limit_window_seconds
)
# Reset emails per address and per client address, so the form cannot flood an inbox.
reset_email_limiter = FailureLimiter(3, 900)
reset_ip_limiter = FailureLimiter(20, 900)


def reset_login_limits() -> None:
    email_limiter.clear()
    ip_limiter.clear()
    reset_email_limiter.clear()
    reset_ip_limiter.clear()


def _address_keys(meta: RequestMeta) -> tuple[str, ...]:
    """The per-address limiter key, or none when the address is not the client's.

    Without trusted proxy headers, every sign-in through the dashboard arrives from the
    dashboard server's loopback address. Counting those together would let anyone lock
    every user out with a handful of wrong passwords, so only the per-email limit applies.
    """
    if not meta.ip:
        return ()
    if not get_settings().trust_proxy_headers:
        try:
            if ip_address(meta.ip).is_loopback:
                return ()
        except ValueError:
            pass
    return (f"ip:{meta.ip}",)


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    expires_in: int
    refresh_token: str


def _now() -> datetime:
    return datetime.now(UTC)


def _new_refresh(
    user_id: uuid.UUID, family_id: uuid.UUID, meta: RequestMeta
) -> tuple[str, RefreshToken]:
    raw = generate_refresh_token()
    row = RefreshToken(
        user_id=user_id,
        token_hash=hash_token(raw),
        family_id=family_id,
        expires_at=_now() + timedelta(days=get_settings().refresh_token_ttl_days),
        user_agent=meta.user_agent,
        ip_address=meta.ip,
    )
    return raw, row


async def login(
    session: AsyncSession, email: str, password: str, meta: RequestMeta
) -> IssuedTokens:
    email = normalise_email(email)
    ip_keys = _address_keys(meta)
    if email_limiter.is_blocked(email) or ip_limiter.is_blocked(*ip_keys):
        raise RateLimitedError("Too many failed login attempts. Try again later.")

    user = await get_by_email(session, email)
    valid = verify_password(user.password_hash if user else None, password)
    if user is None or not valid or not user.is_active:
        email_limiter.record_failure(email)
        ip_limiter.record_failure(*ip_keys)
        audit.record(
            session,
            action="auth.login_failed",
            actor_id=user.id if user else None,
            meta=meta,
            details={"email": email[:320]},
        )
        await session.commit()
        raise UnauthorizedError("Invalid email or password")

    email_limiter.reset(email)
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = _now()
    raw, row = _new_refresh(user.id, uuid.uuid4(), meta)
    session.add(row)
    audit.record(session, action="auth.login", actor_id=user.id, meta=meta)
    await session.commit()
    access, ttl = create_access_token(user.id)
    return IssuedTokens(access, ttl, raw)


async def _revoke_family(session: AsyncSession, family_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )


async def refresh(session: AsyncSession, raw_token: str | None, meta: RequestMeta) -> IssuedTokens:
    if not raw_token:
        raise UnauthorizedError("Session expired")
    token = await session.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_token(raw_token))
        .with_for_update()
    )
    if token is None:
        raise UnauthorizedError("Session expired")
    if token.revoked_at is not None:
        # A rotated token was presented again: assume theft and end every session in the family.
        await _revoke_family(session, token.family_id)
        audit.record(
            session,
            action="auth.refresh_reuse_detected",
            actor_id=token.user_id,
            meta=meta,
            details={"family_id": str(token.family_id)},
        )
        await session.commit()
        raise UnauthorizedError("Session expired")
    user = await session.get(User, token.user_id)
    if token.expires_at <= _now() or user is None or not user.is_active:
        token.revoked_at = _now()
        await session.commit()
        raise UnauthorizedError("Session expired")

    token.revoked_at = _now()
    raw, row = _new_refresh(user.id, token.family_id, meta)
    session.add(row)
    await session.commit()
    access, ttl = create_access_token(user.id)
    return IssuedTokens(access, ttl, raw)


async def logout(session: AsyncSession, raw_token: str | None, meta: RequestMeta) -> None:
    if not raw_token:
        return
    token = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token))
    )
    if token is None:
        return
    await _revoke_family(session, token.family_id)
    audit.record(session, action="auth.logout", actor_id=token.user_id, meta=meta)
    await session.commit()


async def change_password(
    session: AsyncSession, user: User, current: str, new: str, meta: RequestMeta
) -> None:
    if not verify_password(user.password_hash, current):
        raise AppError("Current password is incorrect", code="invalid_password")
    if current == new:
        raise AppError("New password must differ from the current one", code="password_unchanged")
    user.password_hash = hash_password(new)
    # Sign out every other session.
    await _revoke_sessions(session, user.id)
    audit.record(session, action="auth.password_changed", actor_id=user.id, meta=meta)
    await session.commit()


_RESET_INVALID = "This reset link is not valid or has expired"


async def _revoke_sessions(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )


async def request_password_reset(
    session: AsyncSession, email: str, meta: RequestMeta
) -> tuple[str, str] | None:
    """Create a reset link for an active account.

    Returns the address and the message to send, or None. The caller sends it after the
    response, and answers the same way whatever happens, so the form never reveals
    whether an account exists.
    """
    settings = get_settings()
    email = normalise_email(email)
    ip_keys = _address_keys(meta)
    if not settings.email_enabled:
        return None
    if reset_email_limiter.is_blocked(email) or reset_ip_limiter.is_blocked(*ip_keys):
        return None
    reset_email_limiter.record_failure(email)
    reset_ip_limiter.record_failure(*ip_keys)
    user = await get_by_email(session, email)
    if user is None or not user.is_active:
        return None
    # Only the newest link works.
    await session.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=_now())
    )
    token = secrets.token_urlsafe(32)
    session.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=_now() + timedelta(minutes=settings.password_reset_ttl_minutes),
        )
    )
    audit.record(session, action="auth.password_reset_requested", actor_id=user.id, meta=meta)
    await session.commit()
    link = f"{settings.public_base_url.rstrip('/')}/reset-password#token={token}"
    body = (
        f"Someone asked to reset the password for your {settings.app_name} account.\n\n"
        f"Open this link to choose a new password:\n{link}\n\n"
        f"The link works once and expires in {settings.password_reset_ttl_minutes} minutes. "
        "If you did not ask for this, ignore this email; your password stays the same.\n"
    )
    return user.email, body


async def send_reset_email(message: tuple[str, str] | None) -> None:
    if message is not None:
        await send_email(message[0], "Reset your password", message[1])


async def confirm_password_reset(
    session: AsyncSession, token: str, new_password: str, meta: RequestMeta
) -> None:
    row = await session.scalar(
        select(PasswordResetToken)
        .where(PasswordResetToken.token_hash == hash_token(token))
        .with_for_update()
    )
    if row is None or row.used_at is not None or row.expires_at <= _now():
        raise NotFoundError(_RESET_INVALID)
    user = await session.get(User, row.user_id)
    if user is None or not user.is_active:
        raise NotFoundError(_RESET_INVALID)
    row.used_at = _now()
    user.password_hash = hash_password(new_password)
    await _revoke_sessions(session, user.id)
    audit.record(session, action="auth.password_reset", actor_id=user.id, meta=meta)
    await session.commit()
    email_limiter.reset(user.email)
