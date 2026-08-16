from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Request

from bifrostnms.auth.audit import (
    AuditActorType,
    AuditOutcome,
    _validate_metadata,
    record_audit_event,
)
from bifrostnms.models import AuditEvent, Realm, User


def request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [(b"user-agent", b"audit-test")],
            "client": ("192.0.2.1", 1234),
            "server": ("testserver", 80),
            "scheme": "https",
            "query_string": b"",
        }
    )


@pytest.mark.parametrize(
    "metadata",
    [
        {"password": "value"},
        {"nested": {"access_token": "value"}},
        {"items": [{"client-secret": "value"}]},
        {"authorization_header": "value"},
    ],
)
def test_validate_metadata_rejects_sensitive_keys(metadata: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="Sensitive audit metadata key"):
        _validate_metadata(metadata)


def test_validate_metadata_allows_identifiers_and_safe_context() -> None:
    _validate_metadata({"changed_fields": ["name", "interval"], "revision": 4})


@pytest.mark.asyncio
async def test_record_audit_event_captures_bounded_request_context() -> None:
    realm = cast(Realm, SimpleNamespace())
    user = cast(User, SimpleNamespace())
    event = cast(AuditEvent, SimpleNamespace())
    with patch(
        "bifrostnms.auth.audit.AuditEvent.create",
        new=AsyncMock(return_value=event),
    ) as create:
        result = await record_audit_event(
            action="realm.member.update",
            outcome=AuditOutcome.SUCCESS,
            actor_type=AuditActorType.USER,
            request=request(),
            realm=realm,
            actor_user=user,
            target_type="realm_membership",
            target_id="membership-id",
            superuser_bypass=True,
            metadata={"changed_fields": ["role"]},
        )

    assert result is event
    assert create.await_args is not None
    assert create.await_args.kwargs["source_ip"] == "192.0.2.1"
    assert create.await_args.kwargs["user_agent"] == "audit-test"
    assert create.await_args.kwargs["superuser_bypass"] is True
    assert create.await_args.kwargs["actor_type"] == "user"
