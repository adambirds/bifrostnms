import pytest

from bifrostnms.email.base import EmailMessage, build_mime_message


def test_build_mime_message_text_only() -> None:
    email = build_mime_message(
        EmailMessage(
            to=["one@example.com", "two@example.com"],
            subject="Test subject",
            text="Hello world",
            reply_to="support@example.com",
            headers={"X-Bifrost-Test": "yes"},
        ),
        from_email="bifrost@example.com",
        from_name="BifrostNMS",
    )

    assert email["From"] == "BifrostNMS <bifrost@example.com>"
    assert email["To"] == "one@example.com, two@example.com"
    assert email["Subject"] == "Test subject"
    assert email["Reply-To"] == "support@example.com"
    assert email["X-Bifrost-Test"] == "yes"
    assert "Hello world" in email.get_content()


def test_build_mime_message_with_html_alternative() -> None:
    email = build_mime_message(
        EmailMessage(
            to=["user@example.com"],
            subject="HTML",
            text="Plain text",
            html="<strong>HTML</strong>",
        ),
        from_email="bifrost@example.com",
    )

    assert email.is_multipart()
    parts = list(email.iter_parts())
    assert parts[0].get_content_type() == "text/plain"
    assert parts[1].get_content_type() == "text/html"
    assert "Plain text" in parts[0].get_content()
    assert "<strong>HTML</strong>" in parts[1].get_content()


def test_build_mime_message_requires_recipient() -> None:
    with pytest.raises(ValueError, match="at least one recipient"):
        build_mime_message(
            EmailMessage(to=[], subject="No recipient", text="Hello"),
            from_email="bifrost@example.com",
        )
