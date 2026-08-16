from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from bifrostnms.schemas.agent_protocol import TlsObservationResult
from bifrostnms.schemas.monitoring import TlsProbeConfiguration

CONTRACT_ROOT = Path(__file__).parents[2] / "contracts" / "probes" / "v1"
CONTRACT_ADAPTER = TypeAdapter(dict[str, Any])


def load_contract(name: str) -> dict[str, Any]:
    return CONTRACT_ADAPTER.validate_python(json.loads((CONTRACT_ROOT / name).read_text()))


def test_tls_configuration_matches_shared_contract() -> None:
    configuration = TlsProbeConfiguration.model_validate(load_contract("tls_configuration.json"))

    assert configuration.port == 8443
    assert configuration.server_name == "monitor.example.com"
    assert configuration.address_family == "auto"
    assert configuration.minimum_tls_version == "1.2"
    assert configuration.expiry_warning_days == 30


def test_tls_result_matches_shared_contract() -> None:
    result = TlsObservationResult.model_validate(load_contract("tls_result.json"))

    assert result.server_name == "monitor.example.com"
    assert result.protocol_version == "TLS 1.3"
    assert result.certificate_present is True
    assert result.hostname_valid is True
    assert result.chain_valid is True
    assert result.fingerprint_sha256 is not None
