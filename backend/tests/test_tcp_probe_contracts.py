import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from bifrostnms.schemas.agent_protocol import TcpObservationResult
from bifrostnms.schemas.monitoring import TcpProbeConfiguration

CONTRACT_ROOT = Path(__file__).parents[2] / "contracts" / "probes" / "v1"
CONTRACT_ADAPTER = TypeAdapter(dict[str, Any])


def load_contract(name: str) -> dict[str, Any]:
    return CONTRACT_ADAPTER.validate_python(json.loads((CONTRACT_ROOT / name).read_text()))


def test_tcp_configuration_matches_shared_contract() -> None:
    configuration = TcpProbeConfiguration.model_validate(load_contract("tcp_configuration.json"))

    assert configuration.schema_version == 1
    assert configuration.port == 443
    assert configuration.address_family == "auto"


def test_tcp_result_matches_shared_contract() -> None:
    result = TcpObservationResult.model_validate(load_contract("tcp_result.json"))

    assert result.port == 443
    assert result.address_used == "2001:db8::1"
    assert result.connect_ms == 12.5
