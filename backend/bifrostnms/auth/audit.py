from __future__ import annotations

from enum import StrEnum
from typing import Any

from fastapi import Request

from bifrostnms.models import AuditEvent, Realm, User


class AuditActorType(StrEnum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"
    ANONYMOUS = "anonymous"


class AuditOutcome(StrEnum):
    SUCCESS = "success"
    DENIED = "denied"
    FAILURE = "failure"


SENSITIVE_METADATA_PARTS = frozenset(
    {"authorization", "cookie", "credential", "password", "secret", "token"}
)


def _validate_metadata(value: object, *, path: str = "metadata") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).lower().replace("-", "_")
            if any(part in normalized for part in SENSITIVE_METADATA_PARTS):
                raise ValueError(f"Sensitive audit metadata key rejected: {path}.{key}")
            _validate_metadata(nested, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _validate_metadata(nested, path=f"{path}[{index}]")


async def record_audit_event(
    *,
    action: str,
    outcome: AuditOutcome,
    actor_type: AuditActorType,
    request: Request | None = None,
    realm: Realm | None = None,
    actor_user: User | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    superuser_bypass: bool = False,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    """Append a structured audit event without accepting sensitive metadata."""
    details = metadata or {}
    _validate_metadata(details)
    source_ip = request.client.host if request is not None and request.client else None
    user_agent = request.headers.get("user-agent", "")[:512] if request is not None else ""
    return await AuditEvent.create(
        realm=realm,
        actor_user=actor_user,
        actor_type=actor_type.value,
        action=action,
        outcome=outcome.value,
        target_type=target_type,
        target_id=target_id,
        source_ip=source_ip,
        user_agent=user_agent,
        superuser_bypass=superuser_bypass,
        metadata=details,
    )
