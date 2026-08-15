from types import SimpleNamespace
from unittest.mock import patch

import pytest

from bifrostnms.email import get_email_backend
from bifrostnms.email.microsoft_graph import MicrosoftGraphEmailBackend
from bifrostnms.email.smtp import SMTPEmailBackend


def test_selects_smtp_backend():
    settings = SimpleNamespace(
        email_backend="smtp",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_security="starttls",
        smtp_timeout_seconds=15.0,
        smtp_from_email="bifrost@example.com",
        smtp_from_name="BifrostNMS",
        smtp_username=None,
        smtp_password=None,
    )

    with patch("bifrostnms.email.get_settings", return_value=settings):
        backend = get_email_backend()

    assert isinstance(backend, SMTPEmailBackend)
    assert backend.host == "smtp.example.com"
    assert backend.authenticated is False


def test_selects_microsoft_graph_backend():
    settings = SimpleNamespace(
        email_backend="microsoft_graph",
        microsoft_graph_private_key_base64="",
        microsoft_graph_private_key_path="/private.pem",
        microsoft_graph_certificate_base64="",
        microsoft_graph_certificate_path="/cert.pem",
        microsoft_graph_tenant_id="tenant",
        microsoft_graph_client_id="client",
        microsoft_graph_sender_email="bifrost@example.com",
        microsoft_graph_private_key_passphrase=None,
        microsoft_graph_from_name="BifrostNMS",
        microsoft_graph_timeout_seconds=15.0,
    )

    with (
        patch("bifrostnms.email.get_settings", return_value=settings),
        patch(
            "bifrostnms.email.read_pem_credential",
            side_effect=[
                "-----BEGIN PRIVATE KEY-----\nkey\n",
                "-----BEGIN CERTIFICATE-----\ncert\n",
            ],
        ),
    ):
        backend = get_email_backend()

    assert isinstance(backend, MicrosoftGraphEmailBackend)
    assert backend.tenant_id == "tenant"
    assert backend.client_id == "client"
    assert backend.sender_email == "bifrost@example.com"


def test_unknown_email_backend_is_rejected():
    settings = SimpleNamespace(email_backend="carrier_pigeon")

    with patch("bifrostnms.email.get_settings", return_value=settings):
        with pytest.raises(ValueError, match="Unsupported email backend"):
            get_email_backend()
