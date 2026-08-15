from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage as StdlibEmailMessage
from typing import Literal

from bifrostnms.email.base import EmailMessage, build_mime_message

SMTP_SECURITY = Literal["none", "starttls", "ssl"]


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
            raise ValueError(
                "SMTP username and password must either both be set or both be omitted"
            )
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
        email = build_mime_message(
            message,
            from_email=self.from_email,
            from_name=self.from_name,
        )
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

    def _authenticate_and_send(
        self,
        client: smtplib.SMTP,
        email: StdlibEmailMessage,
    ) -> None:
        if self.authenticated:
            assert self.username is not None
            assert self.password is not None
            client.login(self.username, self.password)
        client.send_message(email)
