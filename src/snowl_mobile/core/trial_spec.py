from __future__ import annotations

from dataclasses import dataclass

from snowl_mobile.core.enums import ArtifactLevel
from snowl_mobile.core.errors import ConfigError
from snowl_mobile.core.runtime_recipe import RuntimeRecipe
from snowl_mobile.core.states import TrialStatus
from snowl_mobile.schemas.base import SchemaModel


@dataclass(frozen=True, slots=True)
class TrialSpec(SchemaModel):
    trial_id: str
    run_id: str
    benchmark_id: str
    task_id: str
    agent_id: str
    agent_variant: str
    model_id: str
    seed: str
    status: TrialStatus
    artifact_level: ArtifactLevel
    runtime_recipe: RuntimeRecipe
    timeout_sec: int
    max_steps: int

    def validate(self) -> None:
        if not self.trial_id:
            raise ConfigError("trial_id must not be empty", path="trial_spec.trial_id")
        if not self.run_id:
            raise ConfigError("run_id must not be empty", path="trial_spec.run_id")
        if not self.benchmark_id:
            raise ConfigError("benchmark_id must not be empty", path="trial_spec.benchmark_id")
        if not self.task_id:
            raise ConfigError("task_id must not be empty", path="trial_spec.task_id")
        if not self.agent_id:
            raise ConfigError("agent_id must not be empty", path="trial_spec.agent_id")
        if not self.model_id:
            raise ConfigError("model_id must not be empty", path="trial_spec.model_id")
        if not self.seed:
            raise ConfigError("seed must not be empty", path="trial_spec.seed")
        if self.timeout_sec < 1:
            raise ConfigError("timeout_sec must be >= 1", path="trial_spec.timeout_sec")
        if self.max_steps < 1:
            raise ConfigError("max_steps must be >= 1", path="trial_spec.max_steps")
        self.runtime_recipe.validate()
