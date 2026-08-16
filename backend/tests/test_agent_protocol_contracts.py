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
