from __future__ import annotations

import pytest
from pydantic import ValidationError

from bifrostnms.models import ProbeType
from bifrostnms.schemas.monitoring import (
    serialize_probe_configuration,
    validate_probe_configuration,
)


def test_tls_configuration_materializes_secure_defaults() -> None:
    assert serialize_probe_configuration(ProbeType.TLS, {}) == {
        "schema_version": 1,
        "port": 443,
        "server_name": None,
        "address_family": "auto",
        "minimum_tls_version": "1.2",
        "expiry_warning_days": 30,
    }


def test_tls_configuration_preserves_zero_day_expiry_threshold() -> None:
    serialized = serialize_probe_configuration(ProbeType.TLS, {"expiry_warning_days": 0})

    assert serialized["expiry_warning_days"] == 0


def test_tls_configuration_rejects_certificate_verification_bypass() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        validate_probe_configuration(ProbeType.TLS, {"verify_certificate": False})


@pytest.mark.parametrize(
    "configuration",
    [
        {"server_name": "192.0.2.10"},
        {"server_name": "bad..example.com"},
        {"minimum_tls_version": "1.0"},
        {"address_family": "ipx"},
        {"expiry_warning_days": -1},
    ],
)
def test_tls_configuration_rejects_invalid_values(configuration: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        validate_probe_configuration(ProbeType.TLS, configuration)
