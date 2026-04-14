from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from snowl_mobile.schemas.base import SchemaModel


@dataclass(frozen=True, slots=True)
class ActionRecord(SchemaModel):
    agent_raw_output: str | None = None
    parsed_action: dict[str, Any] = field(default_factory=dict)
    executed_action: dict[str, Any] = field(default_factory=dict)
    execution_result: dict[str, Any] = field(default_factory=dict)
