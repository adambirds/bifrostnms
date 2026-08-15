from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage as StdlibEmailMessage
from email.utils import formataddr
from typing import Literal

from bifrostnms.config import get_settings

SMTP_SECURITY = Literal["none", "starttls", "ssl"]


@dataclass(slots=True)
class EmailMessage:
    to: list[str]
    subject: str
    text: str
    html: str | None = None
    reply_to: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


class SMTPEmailBackend:
    """SMTP transport supporting anonymous or authenticated delivery."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        security: SMTP_SECURITY,
        timeout_seconds: float,
        from_email: str,
        from_name: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        if bool(username) != bool(password):
            raise ValueError("SMTP username and password must either both be set or both be omitted")
        if security not in {"none", "starttls", "ssl"}:
            raise ValueError(f"Unsupported SMTP security mode: {security}")

        self.host = host
        self.port = port
        self.security = security
        self.timeout_seconds = timeout_seconds
        self.from_email = from_email
        self.from_name = from_name
        self.username = username
        self.password = password

    @property
    def authenticated(self) -> bool:
        return self.username is not None and self.password is not None

    def send(self, message: EmailMessage) -> None:
        if not message.to:
            raise ValueError("Email message must contain at least one recipient")

        email = StdlibEmailMessage()
        email["From"] = formataddr((self.from_name or "", self.from_email))
        email["To"] = ", ".join(message.to)
        email["Subject"] = message.subject
        if message.reply_to:
            email["Reply-To"] = message.reply_to
        for key, value in message.headers.items():
            email[key] = value

        email.set_content(message.text)
        if message.html:
            email.add_alternative(message.html, subtype="html")

        context = ssl.create_default_context()

        if self.security == "ssl":
            with smtplib.SMTP_SSL(
                self.host,
                self.port,
                timeout=self.timeout_seconds,
                context=context,
            ) as client:
                self._authenticate_and_send(client, email)
            return

        with smtplib.SMTP(self.host, self.port, timeout=self.timeout_seconds) as client:
            client.ehlo()
            if self.security == "starttls":
                client.starttls(context=context)
                client.ehlo()
            self._authenticate_and_send(client, email)

    def _authenticate_and_send(self, client: smtplib.SMTP, email: StdlibEmailMessage) -> None:
        if self.authenticated:
            assert self.username is not None
            assert self.password is not None
            client.login(self.username, self.password)
        client.send_message(email)


def get_email_backend() -> SMTPEmailBackend:
    settings = get_settings()
    return SMTPEmailBackend(
        host=settings.smtp_host,
        port=settings.smtp_port,
        security=settings.smtp_security,
        timeout_seconds=settings.smtp_timeout_seconds,
        from_email=settings.smtp_from_email,
        from_name=settings.smtp_from_name,
        username=settings.smtp_username,
        password=settings.smtp_password,
    )
