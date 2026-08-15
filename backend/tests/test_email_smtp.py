from email.message import EmailMessage as StdlibEmailMessage
from unittest.mock import MagicMock, patch

import pytest

from bifrostnms.email.smtp import EmailMessage, SMTPEmailBackend


def make_backend(**overrides):
    values = {
        "host": "smtp.example.com",
        "port": 587,
        "security": "starttls",
        "timeout_seconds": 10,
        "from_email": "bifrost@example.com",
        "from_name": "BifrostNMS",
        "username": None,
        "password": None,
    }
    values.update(overrides)
    return SMTPEmailBackend(**values)


def test_credentials_must_be_complete():
    with pytest.raises(ValueError, match="both be set or both be omitted"):
        make_backend(username="user")


def test_unauthenticated_starttls_does_not_login():
    client = MagicMock()
    manager = MagicMock()
    manager.__enter__.return_value = client
    manager.__exit__.return_value = False

    with patch("bifrostnms.email.smtp.smtplib.SMTP", return_value=manager):
        make_backend().send(
            EmailMessage(
                to=["user@example.com"],
                subject="Test",
                text="Hello",
            )
        )

    client.starttls.assert_called_once()
    client.login.assert_not_called()
    client.send_message.assert_called_once()


def test_authenticated_starttls_logs_in():
    client = MagicMock()
    manager = MagicMock()
    manager.__enter__.return_value = client
    manager.__exit__.return_value = False

    with patch("bifrostnms.email.smtp.smtplib.SMTP", return_value=manager):
        make_backend(username="user", password="secret").send(
            EmailMessage(
                to=["user@example.com"],
                subject="Test",
                text="Hello",
                html="<p>Hello</p>",
            )
        )

    client.login.assert_called_once_with("user", "secret")
    sent = client.send_message.call_args.args[0]
    assert isinstance(sent, StdlibEmailMessage)
    assert sent["Subject"] == "Test"
    assert sent["To"] == "user@example.com"


def test_ssl_uses_smtp_ssl():
    client = MagicMock()
    manager = MagicMock()
    manager.__enter__.return_value = client
    manager.__exit__.return_value = False

    with patch("bifrostnms.email.smtp.smtplib.SMTP_SSL", return_value=manager) as smtp_ssl:
        make_backend(security="ssl", port=465).send(
            EmailMessage(to=["user@example.com"], subject="Test", text="Hello")
        )

    smtp_ssl.assert_called_once()
    client.starttls.assert_not_called()
    client.send_message.assert_called_once()
