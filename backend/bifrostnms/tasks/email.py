from __future__ import annotations

import requests
from celery import shared_task

from bifrostnms.email import EmailMessage, get_email_backend
from bifrostnms.email.microsoft_graph import MicrosoftGraphDeliveryError


@shared_task(  # type: ignore[untyped-decorator]
    name="bifrostnms.tasks.email.send_email",
    autoretry_for=(OSError, TimeoutError, requests.RequestException, MicrosoftGraphDeliveryError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=5,
    ignore_result=True,
)
def send_email(
    *,
    to: list[str],
    subject: str,
    text: str,
    html: str | None = None,
    reply_to: str | None = None,
    headers: dict[str, str] | None = None,
) -> None:
    """Send one email through the configured backend.

    Callers should pass identifiers rather than ORM objects when a future email
    needs database state. This task intentionally accepts JSON-serialisable data.
    """

    message = EmailMessage(
        to=to,
        subject=subject,
        text=text,
        html=html,
        reply_to=reply_to,
        headers=headers or {},
    )
    get_email_backend().send(message)
