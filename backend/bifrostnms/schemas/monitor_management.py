from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from bifrostnms.models import ProbeType


class MonitorUpdate(BaseModel):
    target_id: UUID
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    probe_type: ProbeType
    interval_seconds: int = Field(ge=1)
    timeout_seconds: int = Field(ge=1)
    configuration: dict[str, Any] = Field(default_factory=dict)
