"""Outgoing email, encapsulated in an `EmailSender`.

Mailpit locally and Amazon SES in deployed environments both speak SMTP, so a
single sender covers both — only the endpoint and credentials differ.
"""

from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from functools import lru_cache

from app.core.config import settings

SES_SMTP_PORT = 587


@dataclass(frozen=True, slots=True)
class SmtpRelay:
    """Resolved SMTP endpoint and credentials for the active provider."""

    host: str | None
    port: int
    use_tls: bool
    username: str | None
    password: str | None
    credentials_required: bool = False


class EmailSender:
    """Sends mail through the resolved relay."""

    def __init__(
        self,
        host: str | None,
        port: int,
        *,
        use_tls: bool,
        username: str | None,
        password: str | None,
        from_email: str,
        from_name: str,
        credentials_required: bool = False,
    ) -> None:
        self._host = host
        self._port = port
        self._use_tls = use_tls
        self._username = username
        self._password = password
        self._from_email = from_email
        self._from_name = from_name
        self._credentials_required = credentials_required

    @property
    def is_configured(self) -> bool:
        """True when a relay is reachable and, if needed, authenticated."""
        if not self._host:
            return False
        if self._credentials_required:
            return bool(self._username and self._password)
        return True

    def send(self, *, to: str, subject: str, html: str, text: str | None = None) -> None:
        if not self.is_configured:
            raise RuntimeError(self._configuration_error())

        message = EmailMessage()
        message["From"] = f"{self._from_name} <{self._from_email}>"
        message["To"] = to
        message["Subject"] = subject
        message.set_content(text or html)
        message.add_alternative(html, subtype="html")

        with smtplib.SMTP(self._host, self._port, timeout=10) as smtp:
            if self._use_tls:
                smtp.starttls()
            if self._username and self._password:
                smtp.login(self._username, self._password)
            smtp.send_message(message)

    def _configuration_error(self) -> str:
        if not self._host:
            return "SMTP_HOST is not configured"
        if self._credentials_required:
            return "SES_SMTP_USERNAME / SES_SMTP_PASSWORD are not configured"
        return "Email transport is not configured"


def _resolve_relay() -> SmtpRelay:
    """Map the configured provider onto a concrete SMTP endpoint."""
    if settings.EMAIL_PROVIDER == "ses":
        return SmtpRelay(
            host=f"email-smtp.{settings.SES_REGION}.amazonaws.com",
            port=SES_SMTP_PORT,
            use_tls=True,
            username=settings.SES_SMTP_USERNAME,
            password=settings.SES_SMTP_PASSWORD,
            credentials_required=True,
        )
    return SmtpRelay(
        host=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        use_tls=settings.SMTP_TLS,
        username=settings.SMTP_USER,
        password=settings.SMTP_PASSWORD,
    )


@lru_cache
def get_email_sender() -> EmailSender:
    relay = _resolve_relay()
    return EmailSender(
        relay.host,
        relay.port,
        use_tls=relay.use_tls,
        username=relay.username,
        password=relay.password,
        from_email=settings.EMAILS_FROM_EMAIL,
        from_name=settings.EMAILS_FROM_NAME or settings.PROJECT_NAME,
        credentials_required=relay.credentials_required,
    )
