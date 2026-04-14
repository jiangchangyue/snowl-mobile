from __future__ import annotations

from dataclasses import dataclass, field

from snowl_mobile.schemas.action import ActionRecord
from snowl_mobile.schemas.base import SchemaModel
from snowl_mobile.schemas.observation import ObservationBundle


@dataclass(frozen=True, slots=True)
class TrajectoryArtifacts(SchemaModel):
    observation_path: str | None = None
    action_path: str | None = None
    screenshot_path: str | None = None
    xml_path: str | None = None
    model_response_text_path: str | None = None
    model_response_json_path: str | None = None


@dataclass(frozen=True, slots=True)
class TrajectoryTimestamps(SchemaModel):
    observed_at: str
    action_at: str
    persisted_at: str


@dataclass(frozen=True, slots=True)
class TrajectoryStep(SchemaModel):
    step_index: int
    attempt: int
    status: str
    observation: ObservationBundle
    action: ActionRecord
    artifacts: TrajectoryArtifacts
    timestamps: TrajectoryTimestamps
    task_instruction: str | None = None
    thought: str | None = None
    action_text: str | None = None
    action_input: dict[str, object] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
