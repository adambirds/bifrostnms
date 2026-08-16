from __future__ import annotations

from typing import Any

MINIMUM_PROTOCOL_VERSION = 1
MAXIMUM_PROTOCOL_VERSION = 1


class AgentProtocolError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        retryable: bool,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}


def require_supported_protocol(protocol_version: int) -> None:
    if MINIMUM_PROTOCOL_VERSION <= protocol_version <= MAXIMUM_PROTOCOL_VERSION:
        return
    raise AgentProtocolError(
        status_code=409,
        code="incompatible_protocol",
        message="Agent protocol version is not supported.",
        retryable=False,
        details={
            "minimum_protocol_version": MINIMUM_PROTOCOL_VERSION,
            "maximum_protocol_version": MAXIMUM_PROTOCOL_VERSION,
        },
    )
