from __future__ import annotations

from dataclasses import dataclass, field
from email.message import EmailMessage as StdlibEmailMessage
from email.utils import formataddr
from typing import Protocol


@dataclass(slots=True)
class EmailMessage:
    """Provider-neutral email message passed to BifrostNMS email backends."""

    to: list[str]
    subject: str
    text: str
    html: str | None = None
    reply_to: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


class EmailBackend(Protocol):
    def send(self, message: EmailMessage) -> None: ...


def build_mime_message(
    message: EmailMessage,
    *,
    from_email: str,
    from_name: str | None = None,
) -> StdlibEmailMessage:
    """Build the RFC 5322/MIME message shared by SMTP and Graph backends."""
    if not message.to:
        raise ValueError("Email message must contain at least one recipient")

    email = StdlibEmailMessage()
    email["From"] = formataddr((from_name or "", from_email))
    email["To"] = ", ".join(message.to)
    email["Subject"] = message.subject
    if message.reply_to:
        email["Reply-To"] = message.reply_to
    for key, value in message.headers.items():
        email[key] = value

    email.set_content(message.text)
    if message.html:
        email.add_alternative(message.html, subtype="html")
    return email
