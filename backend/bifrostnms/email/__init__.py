from __future__ import annotations

from bifrostnms.config import get_settings
from bifrostnms.email.base import EmailBackend, EmailMessage
from bifrostnms.email.microsoft_graph import (
    MicrosoftGraphEmailBackend,
    read_pem_credential,
)
from bifrostnms.email.smtp import SMTPEmailBackend


def get_email_backend() -> EmailBackend:
    settings = get_settings()

    if settings.email_backend == "smtp":
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

    if settings.email_backend == "microsoft_graph":
        private_key = read_pem_credential(
            base64_value=settings.microsoft_graph_private_key_base64,
            path_value=settings.microsoft_graph_private_key_path,
            label="Microsoft Graph private key",
        )
        public_certificate = read_pem_credential(
            base64_value=settings.microsoft_graph_certificate_base64,
            path_value=settings.microsoft_graph_certificate_path,
            label="Microsoft Graph certificate",
        )
        return MicrosoftGraphEmailBackend(
            tenant_id=settings.microsoft_graph_tenant_id or "",
            client_id=settings.microsoft_graph_client_id or "",
            sender_email=settings.microsoft_graph_sender_email or "",
            private_key=private_key,
            public_certificate=public_certificate,
            private_key_passphrase=settings.microsoft_graph_private_key_passphrase,
            from_name=settings.microsoft_graph_from_name,
            timeout_seconds=settings.microsoft_graph_timeout_seconds,
        )

    raise ValueError(f"Unsupported email backend: {settings.email_backend}")


__all__ = [
    "EmailBackend",
    "EmailMessage",
    "MicrosoftGraphEmailBackend",
    "SMTPEmailBackend",
    "get_email_backend",
]
