import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from bifrostnms.schemas.agent_protocol import (
    AgentConfigurationResponse,
    AgentEnrolmentRequest,
    AgentHeartbeatRequest,
    AgentObservationUpload,
    IcmpObservationResult,
)

CONTRACT_ROOT = Path(__file__).parents[2] / "contracts" / "agent" / "v1"


@pytest.mark.parametrize(
    ("filename", "schema"),
    [
        ("enrolment_request.json", AgentEnrolmentRequest),
        ("heartbeat_request.json", AgentHeartbeatRequest),
        ("configuration_response.json", AgentConfigurationResponse),
        ("observation_upload.json", AgentObservationUpload),
    ],
)
def test_python_models_accept_shared_agent_contracts(
    filename: str, schema: type[BaseModel]
) -> None:
    content: dict[str, Any] = json.loads((CONTRACT_ROOT / filename).read_text())
    schema.model_validate(content)
    assert content["protocol_version"] == 1


def test_icmp_observation_accepts_configured_packet_limit() -> None:
    samples = [float(index) for index in range(100)]

    result = IcmpObservationResult(
        packets_sent=100,
        packets_received=100,
        packet_loss_percent=0,
        min_rtt_ms=0,
        avg_rtt_ms=49.5,
        median_rtt_ms=49.5,
        max_rtt_ms=99,
        p95_rtt_ms=94.05,
        jitter_ms=1,
        rtt_samples_ms=samples,
    )

    assert len(result.rtt_samples_ms) == 100
