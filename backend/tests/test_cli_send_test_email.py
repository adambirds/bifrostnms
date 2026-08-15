from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from bifrostnms.cli.send_test_email import build_parser, main


def test_send_test_email_parser_defaults_subject() -> None:
    args = build_parser().parse_args(["user@example.com"])

    assert args.recipient == "user@example.com"
    assert args.subject == "BifrostNMS test email"


def test_send_test_email_queues_task(capsys: pytest.CaptureFixture[str]) -> None:
    task = MagicMock(return_value=SimpleNamespace(id="task-123"))
    with (
        patch("sys.argv", ["send-test-email", "user@example.com", "--subject", "Hello"]),
        patch("bifrostnms.cli.send_test_email.send_email.delay", task),
    ):
        main()

    task.assert_called_once_with(
        to=["user@example.com"],
        subject="Hello",
        text="This is a test email from BifrostNMS.",
        html="<p>This is a test email from <strong>BifrostNMS</strong>.</p>",
    )
    assert "Queued test email task task-123 for user@example.com" in capsys.readouterr().out
