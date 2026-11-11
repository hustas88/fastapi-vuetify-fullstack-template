"""The email transport is configured purely by environment variables."""

import pytest

from app.core import email as email_module
from app.core.config import Settings
from app.core.email import EmailSender, SmtpRelay, _resolve_relay


@pytest.fixture(name="ses_settings")
def ses_settings_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(email_module.settings, "EMAIL_PROVIDER", "ses")
    monkeypatch.setattr(email_module.settings, "SES_REGION", "eu-west-1")
    monkeypatch.setattr(email_module.settings, "SES_SMTP_USERNAME", "ses-user")
    monkeypatch.setattr(email_module.settings, "SES_SMTP_PASSWORD", "ses-secret")


def _sender_from(relay: SmtpRelay) -> EmailSender:
    return EmailSender(
        relay.host,
        relay.port,
        use_tls=relay.use_tls,
        username=relay.username,
        password=relay.password,
        from_email="noreply@example.com",
        from_name="test",
        credentials_required=relay.credentials_required,
    )


@pytest.mark.usefixtures("ses_settings")
def test_ses_relay_is_derived_from_region() -> None:
    relay = _resolve_relay()

    assert relay.host == "email-smtp.eu-west-1.amazonaws.com"
    assert relay.port == 587
    assert relay.use_tls is True
    assert relay.credentials_required is True
    assert relay.username == "ses-user"


def test_smtp_relay_points_at_mailpit_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(email_module.settings, "EMAIL_PROVIDER", "smtp")

    relay = _resolve_relay()

    assert relay.host == "localhost"
    assert relay.port == 1025
    assert relay.use_tls is False
    assert relay.credentials_required is False


@pytest.mark.usefixtures("ses_settings")
def test_ses_without_credentials_is_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(email_module.settings, "SES_SMTP_PASSWORD", None)

    sender = _sender_from(_resolve_relay())

    assert sender.is_configured is False
    with pytest.raises(RuntimeError, match="SES_SMTP_USERNAME"):
        sender.send(to="someone@example.com", subject="hi", html="<p>hi</p>")


def test_smtp_without_host_is_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(email_module.settings, "EMAIL_PROVIDER", "smtp")
    monkeypatch.setattr(email_module.settings, "SMTP_HOST", None)

    sender = _sender_from(_resolve_relay())

    assert sender.is_configured is False
    with pytest.raises(RuntimeError, match="SMTP_HOST"):
        sender.send(to="someone@example.com", subject="hi", html="<p>hi</p>")


def test_provider_switch_is_validated() -> None:
    """An unknown provider must fail at settings construction, not at send time."""
    with pytest.raises(ValueError):
        Settings(_env_file=None, EMAIL_PROVIDER="sendgrid", SECRET_KEY="x" * 32)
