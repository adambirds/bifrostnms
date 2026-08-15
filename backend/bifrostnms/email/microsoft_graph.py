from __future__ import annotations

import base64
import binascii
import logging
from pathlib import Path
from typing import Any
from urllib.parse import quote

import msal
import requests

from bifrostnms.email.base import EmailMessage, build_mime_message

logger = logging.getLogger(__name__)
GRAPH_SCOPE = ["https://graph.microsoft.com/.default"]


class MicrosoftGraphConfigurationError(RuntimeError):
    """Microsoft Graph email settings are incomplete or invalid."""


class MicrosoftGraphDeliveryError(RuntimeError):
    """Microsoft Graph did not accept an email."""


def read_pem_credential(*, base64_value: str | None, path_value: str | None, label: str) -> str:
    """Read a PEM credential from base64 environment data or a file path."""
    encoded = (base64_value or "").strip()
    if encoded:
        try:
            decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError) as exc:
            raise MicrosoftGraphConfigurationError(
                f"{label} base64 value is not valid base64-encoded UTF-8"
            ) from exc
        if "-----BEGIN " not in decoded:
            raise MicrosoftGraphConfigurationError(f"{label} does not contain PEM data")
        return decoded

    raw_path = (path_value or "").strip()
    if not raw_path:
        raise MicrosoftGraphConfigurationError(
            f"Configure {label} using either its base64 value or file path"
        )
    path = Path(raw_path)
    try:
        pem = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MicrosoftGraphConfigurationError(f"Could not read {label}: {path}") from exc
    if "-----BEGIN " not in pem:
        raise MicrosoftGraphConfigurationError(f"{label} file does not contain PEM data")
    return pem


class MicrosoftGraphEmailBackend:
    """Microsoft Graph app-only email transport using an X.509 certificate."""

    def __init__(
        self,
        *,
        tenant_id: str,
        client_id: str,
        sender_email: str,
        private_key: str,
        public_certificate: str,
        private_key_passphrase: str | None = None,
        from_name: str | None = "BifrostNMS",
        timeout_seconds: float = 15.0,
        save_to_sent_items: bool = True,
    ) -> None:
        for name, value in {
            "tenant_id": tenant_id,
            "client_id": client_id,
            "sender_email": sender_email,
            "private_key": private_key,
            "public_certificate": public_certificate,
        }.items():
            if not value.strip():
                raise MicrosoftGraphConfigurationError(f"Microsoft Graph {name} is required")

        self.tenant_id = tenant_id
        self.client_id = client_id
        self.sender_email = sender_email
        self.private_key = private_key
        self.public_certificate = public_certificate
        self.private_key_passphrase = private_key_passphrase
        self.from_name = from_name
        self.timeout_seconds = timeout_seconds
        self.save_to_sent_items = save_to_sent_items

    def _get_access_token(self) -> str:
        credential: dict[str, str] = {
            "private_key": self.private_key,
            "public_certificate": self.public_certificate,
        }
        if self.private_key_passphrase:
            credential["passphrase"] = self.private_key_passphrase

        app = msal.ConfidentialClientApplication(
            client_id=self.client_id,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            client_credential=credential,
        )
        result: dict[str, Any] = app.acquire_token_for_client(scopes=GRAPH_SCOPE)
        access_token = result.get("access_token")
        if not access_token:
            error = result.get("error", "token_acquisition_failed")
            description = result.get("error_description", "Microsoft identity rejected the request")
            logger.error("Microsoft Graph token acquisition failed: %s", error)
            raise MicrosoftGraphDeliveryError(
                f"Could not authenticate Microsoft Graph email service: {description}"
            )
        return str(access_token)

    def send(self, message: EmailMessage) -> None:
        """Send the provider-neutral message as RFC 5322 MIME through Graph."""
        email = build_mime_message(
            message,
            from_email=self.sender_email,
            from_name=self.from_name,
        )
        mime_base64 = base64.b64encode(email.as_bytes()).decode("ascii")
        sender = quote(self.sender_email, safe="")
        access_token = self._get_access_token()

        response = requests.post(
            f"https://graph.microsoft.com/v1.0/users/{sender}/sendMail",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "text/plain",
            },
            data=mime_base64,
            params={"saveToSentItems": str(self.save_to_sent_items).lower()},
            timeout=self.timeout_seconds,
        )
        if response.status_code != 202:
            request_id = response.headers.get("request-id", "unknown")
            logger.error(
                "Microsoft Graph rejected email: status=%s request_id=%s",
                response.status_code,
                request_id,
            )
            raise MicrosoftGraphDeliveryError(
                f"Microsoft Graph rejected the email (status {response.status_code}, "
                f"request ID {request_id})"
            )
