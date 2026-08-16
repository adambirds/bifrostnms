from __future__ import annotations

import pytest
from pydantic import ValidationError

from bifrostnms.models import ProbeType
from bifrostnms.schemas.monitoring import validate_probe_configuration


def test_explicit_dns_resolver_requires_address() -> None:
    with pytest.raises(ValidationError, match="resolver_address is required"):
        validate_probe_configuration(ProbeType.DNS, {"resolver_mode": "explicit"})


def test_system_dns_resolver_rejects_explicit_address() -> None:
    with pytest.raises(ValidationError, match="resolver_address is not permitted"):
        validate_probe_configuration(
            ProbeType.DNS,
            {"resolver_mode": "system", "resolver_address": "127.0.0.1"},
        )


def test_system_dns_resolver_rejects_forced_tcp_transport() -> None:
    with pytest.raises(ValidationError, match="platform resolver transport behavior"):
        validate_probe_configuration(
            ProbeType.DNS,
            {"resolver_mode": "system", "transport": "tcp"},
        )
