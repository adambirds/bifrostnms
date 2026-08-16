from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from bifrostnms.schemas.agent_protocol import HttpObservationResult
from bifrostnms.schemas.monitoring import HttpProbeConfiguration

CONTRACT_ROOT = Path(__file__).parents[2] / "contracts" / "probes" / "v1"
CONTRACT_ADAPTER = TypeAdapter(dict[str, Any])


def load_contract(name: str) -> dict[str, Any]:
    return CONTRACT_ADAPTER.validate_python(json.loads((CONTRACT_ROOT / name).read_text()))


def test_http_configuration_matches_shared_contract() -> None:
    configuration = HttpProbeConfiguration.model_validate(load_contract("http_configuration.json"))

    assert configuration.schema_version == 1
    assert configuration.scheme == "https"
    assert configuration.port == 8443
    assert configuration.maximum_redirects == 5
    assert configuration.address_family == "auto"
    assert configuration.request_headers["Accept"] == "application/json"
    assert configuration.expected_header_values[0].name == "Content-Type"


def test_http_result_matches_shared_contract() -> None:
    result = HttpObservationResult.model_validate(load_contract("http_result.json"))

    assert result.status_code == 200
    assert result.redirect_count == 1
    assert result.tls_ms == 8.25
    assert result.assertions_total == 3
    assert result.assertions_failed == 0
