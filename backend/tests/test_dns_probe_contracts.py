from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from bifrostnms.schemas.agent_protocol import DnsObservationResult
from bifrostnms.schemas.monitoring import DnsProbeConfiguration

CONTRACT_ROOT = Path(__file__).parents[2] / "contracts" / "probes" / "v1"
CONTRACT_ADAPTER = TypeAdapter(dict[str, Any])


def load_contract(name: str) -> dict[str, Any]:
    return CONTRACT_ADAPTER.validate_python(json.loads((CONTRACT_ROOT / name).read_text()))


def test_dns_configuration_matches_shared_contract() -> None:
    configuration = DnsProbeConfiguration.model_validate(load_contract("dns_configuration.json"))

    assert configuration.resolver_mode == "explicit"
    assert configuration.resolver_address == "127.0.0.1"
    assert configuration.resolver_port == 5353
    assert configuration.transport == "udp_with_tcp_fallback"
    assert configuration.query_type == "A"
    assert configuration.expected_answers[0].value == "192.0.2.10"


def test_dns_result_matches_shared_contract() -> None:
    result = DnsObservationResult.model_validate(load_contract("dns_result.json"))

    assert result.resolver_address == "127.0.0.1"
    assert result.response_code == "NOERROR"
    assert result.answer_count == 1
    assert result.answers[0]["value"] == "192.0.2.10"
    assert result.assertions_failed == 0
