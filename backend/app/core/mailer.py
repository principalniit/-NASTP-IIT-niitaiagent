"""Outgoing email through the operator's own SMTP server (no third-party service).

Email is optional: when SMTP_HOST is empty, send_email does nothing and returns False, and
callers fall back to links an administrator can share. Failures are logged without
credentials and never break the request that triggered them.
"""

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _send(to: str, subject: str, body: str) -> None:
    settings = get_settings()
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    port = settings.smtp_port
    context = ssl.create_default_context()
    if port == 465:
        server: smtplib.SMTP = smtplib.SMTP_SSL(
            settings.smtp_host, port, timeout=20, context=context
        )
    else:
        server = smtplib.SMTP(settings.smtp_host, port, timeout=20)
    with server:
        if port != 465 and settings.smtp_starttls:
            server.starttls(context=context)
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        server.send_message(message)


async def send_now(to: str, subject: str, body: str) -> None:
    """Send a plain-text email and raise on failure (for operator tools)."""
    await asyncio.to_thread(_send, to, subject, body)


def failure_hint(exc: BaseException) -> str:
    """What an operator should check after a failed send. Never includes credentials."""
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return (
            "The mail server refused the username or password. For Gmail or Google "
            "Workspace, SMTP_PASSWORD must be an app password, not the account password."
        )
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return (
            "The server refused the sender. SMTP_FROM must be an address this account may send as."
        )
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "The server refused the recipient address."
    if isinstance(exc, ssl.SSLError | smtplib.SMTPServerDisconnected):
        return (
            "The secure connection failed. Use port 587 with SMTP_STARTTLS=true, or port 465 "
            "for implicit TLS."
        )
    if isinstance(exc, TimeoutError | ConnectionError | OSError):
        return (
            "Could not reach the mail server. Check SMTP_HOST and SMTP_PORT, and that the "
            "network or firewall allows outgoing connections on that port."
        )
    return "The mail server reported an error."


async def send_email(to: str, subject: str, body: str) -> bool:
    """Send a plain-text email. Returns whether it was handed to the mail server."""
    if not get_settings().email_enabled:
        return False
    try:
        await send_now(to, subject, body)
    except (OSError, smtplib.SMTPException) as exc:
        logger.warning("Email could not be sent", extra={"error": type(exc).__name__})
        return False
    return True
