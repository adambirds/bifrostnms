import base64
from unittest.mock import MagicMock, patch

import pytest

from bifrostnms.email import EmailMessage
from bifrostnms.email.microsoft_graph import (
    MicrosoftGraphConfigurationError,
    MicrosoftGraphDeliveryError,
    MicrosoftGraphEmailBackend,
    read_pem_credential,
)

PRIVATE_KEY = "-----BEGIN PRIVATE KEY-----\ntest-key\n-----END PRIVATE KEY-----\n"
CERTIFICATE = "-----BEGIN CERTIFICATE-----\ntest-cert\n-----END CERTIFICATE-----\n"


def make_backend(**overrides):
    values = {
        "tenant_id": "tenant-id",
        "client_id": "client-id",
        "sender_email": "bifrost@example.com",
        "private_key": PRIVATE_KEY,
        "public_certificate": CERTIFICATE,
        "from_name": "BifrostNMS",
        "timeout_seconds": 10,
    }
    values.update(overrides)
    return MicrosoftGraphEmailBackend(**values)


def test_reads_base64_pem_credential():
    encoded = base64.b64encode(CERTIFICATE.encode()).decode()
    assert read_pem_credential(base64_value=encoded, path_value=None, label="certificate") == CERTIFICATE


def test_rejects_missing_credentials():
    with pytest.raises(MicrosoftGraphConfigurationError, match="tenant_id is required"):
        make_backend(tenant_id="")


def test_acquires_app_token_with_certificate():
    app = MagicMock()
    app.acquire_token_for_client.return_value = {"access_token": "token"}

    with patch(
        "bifrostnms.email.microsoft_graph.msal.ConfidentialClientApplication",
        return_value=app,
    ) as application:
        token = make_backend(private_key_passphrase="secret")._get_access_token()

    assert token == "token"
    credential = application.call_args.kwargs["client_credential"]
    assert credential["private_key"] == PRIVATE_KEY
    assert credential["public_certificate"] == CERTIFICATE
    assert credential["passphrase"] == "secret"
    app.acquire_token_for_client.assert_called_once_with(
        scopes=["https://graph.microsoft.com/.default"]
    )


def test_sends_mime_message_through_graph():
    response = MagicMock(status_code=202)
    backend = make_backend()

    with (
        patch.object(backend, "_get_access_token", return_value="token"),
        patch("bifrostnms.email.microsoft_graph.requests.post", return_value=response) as post,
    ):
        backend.send(
            EmailMessage(
                to=["user@example.com"],
                subject="Test",
                text="Hello",
                html="<p>Hello</p>",
                reply_to="support@example.com",
            )
        )

    call = post.call_args
    assert call.args[0].endswith("/users/bifrost%40example.com/sendMail")
    assert call.kwargs["headers"]["Authorization"] == "Bearer token"
    assert call.kwargs["headers"]["Content-Type"] == "text/plain"
    assert isinstance(call.kwargs["data"], str)


def test_graph_rejection_raises_delivery_error():
    response = MagicMock(status_code=403)
    response.headers = {"request-id": "request-123"}
    backend = make_backend()

    with (
        patch.object(backend, "_get_access_token", return_value="token"),
        patch("bifrostnms.email.microsoft_graph.requests.post", return_value=response),
        pytest.raises(MicrosoftGraphDeliveryError, match="request-123"),
    ):
        backend.send(EmailMessage(to=["user@example.com"], subject="Test", text="Hello"))
