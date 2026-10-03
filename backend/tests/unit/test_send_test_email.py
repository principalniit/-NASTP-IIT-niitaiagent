"""The send-test-email command checks SMTP settings and explains failures without secrets."""

import smtplib

import pytest
from pydantic import SecretStr

from app.cli import send_test_email
from app.core import mailer
from app.core.config import get_settings


@pytest.fixture
def smtp_on(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.org")
    monkeypatch.setattr(settings, "smtp_from", "SEO <seo@example.org>")
    monkeypatch.setattr(settings, "smtp_username", "seo@example.org")
    monkeypatch.setattr(settings, "smtp_password", SecretStr("app-password-value"))


async def test_email_off_says_what_to_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "smtp_host", "")
    with pytest.raises(SystemExit, match="SMTP_HOST and SMTP_FROM"):
        await send_test_email("someone@example.org")


@pytest.mark.usefixtures("smtp_on")
async def test_a_test_email_is_sent(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sent: list[tuple[str, str, str]] = []
    monkeypatch.setattr(mailer, "_send", lambda to, subject, body: sent.append((to, subject, body)))
    await send_test_email("someone@example.org")
    assert sent and sent[0][0] == "someone@example.org" and "test email" in sent[0][1]
    assert "Sent to someone@example.org" in capsys.readouterr().out


@pytest.mark.usefixtures("smtp_on")
@pytest.mark.parametrize(
    ("error", "hint"),
    [
        (
            smtplib.SMTPAuthenticationError(535, b"Username and Password not accepted"),
            "app password",
        ),
        (ConnectionRefusedError(), "Could not reach the mail server"),
        (smtplib.SMTPServerDisconnected(), "port 587"),
    ],
)
async def test_failures_are_explained(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
    hint: str,
) -> None:
    def refuse(to: str, subject: str, body: str) -> None:
        raise error

    monkeypatch.setattr(mailer, "_send", refuse)
    with pytest.raises(SystemExit) as stopped:
        await send_test_email("someone@example.org")
    message = str(stopped.value)
    assert hint in message
    assert "app-password-value" not in message + capsys.readouterr().out
