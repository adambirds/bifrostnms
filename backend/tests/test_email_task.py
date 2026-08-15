from unittest.mock import MagicMock, patch

from bifrostnms.tasks.email import send_email


def test_email_task_builds_provider_neutral_message() -> None:
    backend = MagicMock()

    with patch("bifrostnms.tasks.email.get_email_backend", return_value=backend):
        send_email.run(
            to=["user@example.com"],
            subject="Security alert",
            text="Plain text",
            html="<p>HTML</p>",
            reply_to="support@example.com",
            headers={"X-Test": "yes"},
        )

    backend.send.assert_called_once()
    message = backend.send.call_args.args[0]
    assert message.to == ["user@example.com"]
    assert message.subject == "Security alert"
    assert message.text == "Plain text"
    assert message.html == "<p>HTML</p>"
    assert message.reply_to == "support@example.com"
    assert message.headers == {"X-Test": "yes"}
