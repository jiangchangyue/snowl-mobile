from __future__ import annotations

from dataclasses import dataclass, field

from snowl_mobile.core.enums import EnvironmentIsolation, ObservationMode, WorkerMode
from snowl_mobile.core.errors import ConfigError
from snowl_mobile.schemas.base import SchemaModel


@dataclass(frozen=True, slots=True)
class RuntimeRecipe(SchemaModel):
    agent_runtime: str
    benchmark_runtime: str
    worker_mode: WorkerMode
    env_isolation: EnvironmentIsolation
    device_profile: str
    reset_policy: str
    observation_mode: ObservationMode
    control_backend: str
    backend_requirements: tuple[str, ...] = ()
    required_env: tuple[str, ...] = ()
    env_vars: dict[str, str] = field(default_factory=dict)
    mounts: tuple[str, ...] = ()
    bridge_id: str = ""
    pair_recipe_id: str = ""
    pair_requires_bridge: bool = False
    ports: dict[str, int] = field(default_factory=dict)
    launch_hints: dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.agent_runtime:
            raise ConfigError("agent_runtime must not be empty", path="runtime_recipe.agent_runtime")
        if not self.benchmark_runtime:
            raise ConfigError(
                "benchmark_runtime must not be empty",
                path="runtime_recipe.benchmark_runtime",
            )
        if not self.device_profile:
            raise ConfigError("device_profile must not be empty", path="runtime_recipe.device_profile")
        if not self.reset_policy:
            raise ConfigError("reset_policy must not be empty", path="runtime_recipe.reset_policy")
        if not self.control_backend:
            raise ConfigError(
                "control_backend must not be empty",
                path="runtime_recipe.control_backend",
            )
        if self.pair_requires_bridge and not self.bridge_id:
            raise ConfigError(
                "pair_requires_bridge cannot be true when bridge_id is empty",
                path="runtime_recipe.bridge_id",
            )
        for port_name, port in self.ports.items():
            if not port_name.strip():
                raise ConfigError("port names must not be empty", path="runtime_recipe.ports")
            if port < 1 or port > 65535:
                raise ConfigError(
                    "ports must be between 1 and 65535",
                    path=f"runtime_recipe.ports.{port_name}",
                )
