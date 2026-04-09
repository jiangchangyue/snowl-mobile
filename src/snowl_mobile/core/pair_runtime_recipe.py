from __future__ import annotations

from dataclasses import dataclass, field, replace

from snowl_mobile.core.enums import EnvironmentIsolation, ObservationMode, WorkerMode
from snowl_mobile.core.errors import ConfigError
from snowl_mobile.core.runtime_recipe import RuntimeRecipe
from snowl_mobile.core.validation import (
    expect_bool,
    expect_enum_member,
    expect_mapping,
    expect_mapping_of_strings,
    expect_string,
    expect_string_list,
    get_optional,
    get_required,
)
from snowl_mobile.schemas.base import SchemaModel


def _expect_port_mapping(value: object, path: str) -> dict[str, int]:
    mapping = expect_mapping(value, path)
    normalized: dict[str, int] = {}
    for key, raw in mapping.items():
        port_name = expect_string(key, f"{path}.<key>")
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise ConfigError("expected an integer port", path=f"{path}.{port_name}")
        if raw < 1 or raw > 65535:
            raise ConfigError("port must be between 1 and 65535", path=f"{path}.{port_name}")
        normalized[port_name] = raw
    return normalized


def _merge_unique(base: tuple[str, ...], extra: tuple[str, ...]) -> tuple[str, ...]:
    merged: list[str] = []
    seen: set[str] = set()
    for value in (*base, *extra):
        if value in seen:
            continue
        seen.add(value)
        merged.append(value)
    return tuple(merged)


@dataclass(frozen=True, slots=True)
class PairRuntimeRecipeSpec(SchemaModel):
    recipe_id: str
    agent_id: str
    benchmark_id: str
    bridge_id: str = ""
    requires_bridge: bool = False
    worker_mode: WorkerMode | None = None
    env_isolation: EnvironmentIsolation | None = None
    observation_mode: ObservationMode | None = None
    device_profile: str = ""
    control_backend: str = ""
    reset_policy: str = ""
    backend_requirements: tuple[str, ...] = ()
    required_env: tuple[str, ...] = ()
    env_vars: dict[str, str] = field(default_factory=dict)
    mounts: tuple[str, ...] = ()
    ports: dict[str, int] = field(default_factory=dict)
    launch_hints: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: dict[str, object], path: str) -> "PairRuntimeRecipeSpec":
        raw_worker_mode = get_optional(data, "worker_mode", None)
        raw_env_isolation = get_optional(data, "env_isolation", None)
        raw_observation_mode = get_optional(data, "observation_mode", None)
        spec = cls(
            recipe_id=expect_string(get_required(data, "recipe_id", path, aliases=("id",)), f"{path}.recipe_id"),
            agent_id=expect_string(get_required(data, "agent_id", path), f"{path}.agent_id"),
            benchmark_id=expect_string(get_required(data, "benchmark_id", path), f"{path}.benchmark_id"),
            bridge_id=expect_string(get_optional(data, "bridge_id", ""), f"{path}.bridge_id", allow_empty=True),
            requires_bridge=expect_bool(get_optional(data, "requires_bridge", False), f"{path}.requires_bridge"),
            worker_mode=None
            if raw_worker_mode is None
            else expect_enum_member(raw_worker_mode, f"{path}.worker_mode", WorkerMode),
            env_isolation=None
            if raw_env_isolation is None
            else expect_enum_member(raw_env_isolation, f"{path}.env_isolation", EnvironmentIsolation),
            observation_mode=None
            if raw_observation_mode is None
            else expect_enum_member(raw_observation_mode, f"{path}.observation_mode", ObservationMode),
            device_profile=expect_string(get_optional(data, "device_profile", ""), f"{path}.device_profile", allow_empty=True),
            control_backend=expect_string(get_optional(data, "control_backend", ""), f"{path}.control_backend", allow_empty=True),
            reset_policy=expect_string(get_optional(data, "reset_policy", ""), f"{path}.reset_policy", allow_empty=True),
            backend_requirements=expect_string_list(
                get_optional(data, "backend_requirements", []),
                f"{path}.backend_requirements",
            ),
            required_env=expect_string_list(
                get_optional(data, "required_env", []),
                f"{path}.required_env",
            ),
            env_vars=expect_mapping_of_strings(
                get_optional(data, "env_vars", {}),
                f"{path}.env_vars",
            ),
            mounts=expect_string_list(get_optional(data, "mounts", []), f"{path}.mounts"),
            ports=_expect_port_mapping(get_optional(data, "ports", {}), f"{path}.ports"),
            launch_hints=expect_mapping_of_strings(
                get_optional(data, "launch_hints", {}),
                f"{path}.launch_hints",
            ),
        )
        spec.validate(path)
        return spec

    def validate(self, path: str) -> None:
        if self.requires_bridge and not self.bridge_id:
            raise ConfigError(
                "requires_bridge cannot be true when bridge_id is empty",
                path=f"{path}.bridge_id",
            )

    def matches(self, agent_id: str, benchmark_id: str) -> bool:
        return self.agent_id == agent_id and self.benchmark_id == benchmark_id

    def apply_to(self, base_recipe: RuntimeRecipe) -> RuntimeRecipe:
        merged_recipe = replace(
            base_recipe,
            worker_mode=self.worker_mode or base_recipe.worker_mode,
            env_isolation=self.env_isolation or base_recipe.env_isolation,
            observation_mode=self.observation_mode or base_recipe.observation_mode,
            device_profile=self.device_profile or base_recipe.device_profile,
            control_backend=self.control_backend or base_recipe.control_backend,
            reset_policy=self.reset_policy or base_recipe.reset_policy,
            backend_requirements=_merge_unique(base_recipe.backend_requirements, self.backend_requirements),
            required_env=_merge_unique(base_recipe.required_env, self.required_env),
            env_vars={**base_recipe.env_vars, **self.env_vars},
            mounts=_merge_unique(base_recipe.mounts, self.mounts),
            bridge_id=self.bridge_id or base_recipe.bridge_id,
            pair_recipe_id=self.recipe_id,
            pair_requires_bridge=self.requires_bridge or base_recipe.pair_requires_bridge,
            ports={**base_recipe.ports, **self.ports},
            launch_hints={**base_recipe.launch_hints, **self.launch_hints},
        )
        merged_recipe.validate()
        return merged_recipe
