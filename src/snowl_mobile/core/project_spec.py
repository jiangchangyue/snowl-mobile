from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from snowl_mobile.core.agent_spec import AgentSpec
from snowl_mobile.core.benchmark_spec import BenchmarkSpec
from snowl_mobile.core.enums import DeviceMode, EnvironmentIsolation, ObservationMode, WorkerMode
from snowl_mobile.core.errors import ConfigError
from snowl_mobile.core.pair_runtime_recipe import PairRuntimeRecipeSpec
from snowl_mobile.core.policies import ArtifactPolicy, ResetPolicy, RetryPolicy
from snowl_mobile.core.runtime_recipe import RuntimeRecipe
from snowl_mobile.core.validation import (
    ensure_unique,
    expect_bool,
    expect_enum_member,
    expect_int,
    expect_list,
    expect_mapping,
    expect_string,
    expect_string_list,
    get_optional,
    get_required,
)
from snowl_mobile.devices.emulator_profile import EmulatorProfile
from snowl_mobile.models.model_spec import ModelSpec
from snowl_mobile.schemas.base import SchemaModel


@dataclass(frozen=True, slots=True)
class ProjectMetadata(SchemaModel):
    name: str
    run_name: str
    description: str = ""

    @classmethod
    def from_mapping(cls, data: dict[str, object], path: str) -> "ProjectMetadata":
        return cls(
            name=expect_string(get_required(data, "name", path), f"{path}.name"),
            run_name=expect_string(get_required(data, "run_name", path), f"{path}.run_name"),
            description=expect_string(
                get_optional(data, "description", ""),
                f"{path}.description",
                allow_empty=True,
            ),
        )


@dataclass(frozen=True, slots=True)
class MatrixSpec(SchemaModel):
    expand: str = "agent_x_benchmark"
    seeds: tuple[str, ...] = ("default-seed",)

    @classmethod
    def from_mapping(cls, data: dict[str, object], path: str) -> "MatrixSpec":
        spec = cls(
            expand=expect_string(get_optional(data, "expand", "agent_x_benchmark"), f"{path}.expand"),
            seeds=expect_string_list(get_optional(data, "seeds", ["default-seed"]), f"{path}.seeds", allow_empty=False),
        )
        if spec.expand != "agent_x_benchmark":
            raise ConfigError(
                "only 'agent_x_benchmark' matrix expansion is supported in the current contract layer",
                path=f"{path}.expand",
            )
        return spec


@dataclass(frozen=True, slots=True)
class RuntimeSettings(SchemaModel):
    batch_size: int
    default_worker_mode: WorkerMode
    observation_mode: ObservationMode
    env_isolation: EnvironmentIsolation
    max_steps: int
    timeout_sec: int

    @classmethod
    def from_mapping(cls, data: dict[str, object], path: str) -> "RuntimeSettings":
        return cls(
            batch_size=expect_int(get_optional(data, "batch_size", 1), f"{path}.batch_size", minimum=1),
            default_worker_mode=expect_enum_member(
                get_optional(data, "default_worker_mode", get_optional(data, "worker_mode", WorkerMode.IN_PROCESS.value)),
                f"{path}.default_worker_mode",
                WorkerMode,
            ),
            observation_mode=expect_enum_member(
                get_optional(data, "observation_mode", ObservationMode.IMAGE_TEXT.value),
                f"{path}.observation_mode",
                ObservationMode,
            ),
            env_isolation=expect_enum_member(
                get_optional(data, "env_isolation", EnvironmentIsolation.PER_WORKER_VENV.value),
                f"{path}.env_isolation",
                EnvironmentIsolation,
            ),
            max_steps=expect_int(get_optional(data, "max_steps", 1), f"{path}.max_steps", minimum=1),
            timeout_sec=expect_int(
                get_optional(data, "timeout_sec", 60),
                f"{path}.timeout_sec",
                minimum=1,
            ),
        )


@dataclass(frozen=True, slots=True)
class DeviceSettings(SchemaModel):
    emulator_profiles: tuple[EmulatorProfile, ...]
    default_profile: str
    control_backend: str
    device_mode: DeviceMode = DeviceMode.FAKE
    adb_serials: tuple[str, ...] = ()
    avd_names: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, data: dict[str, object], path: str) -> "DeviceSettings":
        profiles_raw = expect_list(get_required(data, "emulator_profiles", path), f"{path}.emulator_profiles")
        profiles = tuple(
            EmulatorProfile.from_mapping(
                expect_mapping(profile, f"{path}.emulator_profiles[{index}]"),
                f"{path}.emulator_profiles[{index}]",
            )
            for index, profile in enumerate(profiles_raw)
        )
        settings = cls(
            emulator_profiles=profiles,
            default_profile=expect_string(
                get_required(data, "default_profile", path),
                f"{path}.default_profile",
            ),
            control_backend=expect_string(
                get_required(data, "control_backend", path),
                f"{path}.control_backend",
            ),
            device_mode=expect_enum_member(
                get_optional(data, "device_mode", DeviceMode.FAKE.value),
                f"{path}.device_mode",
                DeviceMode,
            ),
            adb_serials=cls._parse_string_list_aliases(
                data,
                path=f"{path}.adb_serials",
                primary_key="adb_serials",
                singular_alias="adb_serial",
            ),
            avd_names=cls._parse_string_list_aliases(
                data,
                path=f"{path}.avd_names",
                primary_key="avd_names",
                singular_alias="avd_name",
            ),
        )
        settings.validate(path)
        return settings

    def validate(self, path: str) -> None:
        ensure_unique((profile.profile_id for profile in self.emulator_profiles), f"{path}.emulator_profiles", "emulator profile ids")
        ensure_unique(self.adb_serials, f"{path}.adb_serials", "adb serials")
        ensure_unique(self.avd_names, f"{path}.avd_names", "avd names")
        if self.default_profile not in {profile.profile_id for profile in self.emulator_profiles}:
            raise ConfigError(
                f"default_profile '{self.default_profile}' is not declared under emulator_profiles",
                path=f"{path}.default_profile",
            )
        if self.device_mode == DeviceMode.MANAGED_AVD and not self.avd_names:
            profile_names = {profile.base_avd_name for profile in self.emulator_profiles}
            if not profile_names:
                raise ConfigError(
                    "managed_avd mode requires at least one avd_name or emulator profile base_avd_name",
                    path=f"{path}.device_mode",
                )

    @staticmethod
    def _parse_string_list_aliases(
        data: dict[str, object],
        *,
        path: str,
        primary_key: str,
        singular_alias: str,
    ) -> tuple[str, ...]:
        raw = get_optional(data, primary_key, None, aliases=(singular_alias,))
        if raw is None:
            return ()
        if isinstance(raw, str):
            return (expect_string(raw, path),)
        return expect_string_list(raw, path)


@dataclass(frozen=True, slots=True)
class MonitoringConfig(SchemaModel):
    cli_live_panel: bool = True
    web_viewer: bool = False

    @classmethod
    def from_mapping(cls, data: dict[str, object], path: str) -> "MonitoringConfig":
        return cls(
            cli_live_panel=expect_bool(
                get_optional(data, "cli_live_panel", True),
                f"{path}.cli_live_panel",
            ),
            web_viewer=expect_bool(get_optional(data, "web_viewer", False), f"{path}.web_viewer"),
        )


@dataclass(frozen=True, slots=True)
class ProjectSpec(SchemaModel):
    project: ProjectMetadata
    models: tuple[ModelSpec, ...]
    agents: tuple[AgentSpec, ...]
    benchmarks: tuple[BenchmarkSpec, ...]
    pair_runtime_recipes: tuple[PairRuntimeRecipeSpec, ...]
    matrix: MatrixSpec
    runtime: RuntimeSettings
    devices: DeviceSettings
    reset: ResetPolicy
    retries: RetryPolicy
    artifacts: ArtifactPolicy
    monitoring: MonitoringConfig

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "ProjectSpec":
        spec = cls(
            project=ProjectMetadata.from_mapping(
                expect_mapping(get_required(data, "project", "project"), "project"),
                "project",
            ),
            models=tuple(
                ModelSpec.from_mapping(
                    expect_mapping(model, f"models[{index}]"),
                    f"models[{index}]",
                )
                for index, model in enumerate(expect_list(get_required(data, "models", "models"), "models"))
            ),
            agents=tuple(
                AgentSpec.from_mapping(
                    expect_mapping(agent, f"agents[{index}]"),
                    f"agents[{index}]",
                )
                for index, agent in enumerate(expect_list(get_required(data, "agents", "agents"), "agents"))
            ),
            benchmarks=tuple(
                BenchmarkSpec.from_mapping(
                    expect_mapping(benchmark, f"benchmarks[{index}]"),
                    f"benchmarks[{index}]",
                )
                for index, benchmark in enumerate(
                    expect_list(get_required(data, "benchmarks", "benchmarks"), "benchmarks")
                )
            ),
            pair_runtime_recipes=tuple(
                PairRuntimeRecipeSpec.from_mapping(
                    expect_mapping(recipe, f"pair_runtime_recipes[{index}]"),
                    f"pair_runtime_recipes[{index}]",
                )
                for index, recipe in enumerate(
                    expect_list(
                        get_optional(data, "pair_runtime_recipes", []),
                        "pair_runtime_recipes",
                    )
                )
            ),
            matrix=MatrixSpec.from_mapping(
                expect_mapping(get_required(data, "matrix", "matrix"), "matrix"),
                "matrix",
            ),
            runtime=RuntimeSettings.from_mapping(
                expect_mapping(get_required(data, "runtime", "runtime"), "runtime"),
                "runtime",
            ),
            devices=DeviceSettings.from_mapping(
                expect_mapping(get_required(data, "devices", "devices"), "devices"),
                "devices",
            ),
            reset=ResetPolicy.from_mapping(
                expect_mapping(get_required(data, "reset", "reset"), "reset"),
                "reset",
            ),
            retries=RetryPolicy.from_mapping(
                expect_mapping(get_required(data, "retries", "retries"), "retries"),
                "retries",
            ),
            artifacts=ArtifactPolicy.from_mapping(
                expect_mapping(get_required(data, "artifacts", "artifacts"), "artifacts"),
                "artifacts",
            ),
            monitoring=MonitoringConfig.from_mapping(
                expect_mapping(get_required(data, "monitoring", "monitoring"), "monitoring"),
                "monitoring",
            ),
        )
        spec.validate()
        return spec

    def validate(self) -> None:
        if not self.models:
            raise ConfigError("project config must include at least one model", path="models")
        if not self.agents:
            raise ConfigError("project config must include at least one agent", path="agents")
        if not self.benchmarks:
            raise ConfigError("project config must include at least one benchmark", path="benchmarks")

        ensure_unique((model.model_id for model in self.models), "models", "model ids")
        ensure_unique((agent.variant_id for agent in self.agents), "agents", "agent variant ids")
        ensure_unique((benchmark.benchmark_id for benchmark in self.benchmarks), "benchmarks", "benchmark ids")
        ensure_unique(
            (recipe.recipe_id for recipe in self.pair_runtime_recipes),
            "pair_runtime_recipes",
            "pair runtime recipe ids",
        )
        ensure_unique(
            (f"{recipe.agent_id}::{recipe.benchmark_id}" for recipe in self.pair_runtime_recipes),
            "pair_runtime_recipes",
            "pair runtime recipe pairs",
        )

        known_model_ids = {model.model_id for model in self.models}
        known_agent_ids = {agent.agent_id for agent in self.agents}
        known_benchmark_ids = {benchmark.benchmark_id for benchmark in self.benchmarks}
        model_index = {model.model_id: model for model in self.models}

        for index, agent in enumerate(self.agents):
            if agent.model_ref not in known_model_ids:
                raise ConfigError(
                    f"references unknown model '{agent.model_ref}'",
                    path=f"agents[{index}].model_ref",
                )
            model = model_index[agent.model_ref]
            issues = agent.model_compatibility_issues(model)
            if issues:
                raise ConfigError("; ".join(issues), path=f"agents[{index}]")

        for index, benchmark in enumerate(self.benchmarks):
            if benchmark.reset_policy != self.reset.name:
                raise ConfigError(
                    f"benchmark reset_policy '{benchmark.reset_policy}' does not match declared reset policy '{self.reset.name}'",
                    path=f"benchmarks[{index}].reset_policy",
                )
            if benchmark.device_backend != self.devices.control_backend:
                raise ConfigError(
                    f"benchmark device_backend '{benchmark.device_backend}' does not match configured control_backend '{self.devices.control_backend}'",
                    path=f"benchmarks[{index}].device_backend",
                )
            unknown_agents = set(benchmark.supported_agent_ids) - known_agent_ids
            if unknown_agents:
                unknown = ", ".join(sorted(unknown_agents))
                raise ConfigError(
                    f"supported_agent_ids references unknown agents: {unknown}",
                    path=f"benchmarks[{index}].supported_agent_ids",
                )
        for index, agent in enumerate(self.agents):
            if agent.supported_backends and self.devices.control_backend not in agent.supported_backends:
                raise ConfigError(
                    f"agent supported_backends does not include configured control_backend '{self.devices.control_backend}'",
                    path=f"agents[{index}].supported_backends",
                )
        valid_profiles = {profile.profile_id for profile in self.devices.emulator_profiles}
        for index, recipe in enumerate(self.pair_runtime_recipes):
            if recipe.agent_id not in known_agent_ids:
                raise ConfigError(
                    f"pair runtime recipe references unknown agent '{recipe.agent_id}'",
                    path=f"pair_runtime_recipes[{index}].agent_id",
                )
            if recipe.benchmark_id not in known_benchmark_ids:
                raise ConfigError(
                    f"pair runtime recipe references unknown benchmark '{recipe.benchmark_id}'",
                    path=f"pair_runtime_recipes[{index}].benchmark_id",
                )
            if recipe.device_profile and recipe.device_profile not in valid_profiles:
                raise ConfigError(
                    f"pair runtime recipe references unknown device_profile '{recipe.device_profile}'",
                    path=f"pair_runtime_recipes[{index}].device_profile",
                )

    def freeze_snapshot(self) -> dict[str, Any]:
        return self.to_dict()

    def build_runtime_recipe(self, agent: AgentSpec, benchmark: BenchmarkSpec) -> RuntimeRecipe:
        benchmark_ports, benchmark_launch_hints = self._benchmark_runtime_hints(benchmark)
        recipe = RuntimeRecipe(
            agent_runtime=agent.variant_id,
            benchmark_runtime=benchmark.benchmark_id,
            worker_mode=agent.worker_mode or self.runtime.default_worker_mode,
            env_isolation=self.runtime.env_isolation,
            device_profile=self.devices.default_profile,
            reset_policy=self.reset.name,
            observation_mode=self.runtime.observation_mode,
            control_backend=self.devices.control_backend,
            backend_requirements=(benchmark.device_backend,),
            required_env=tuple(sorted(set(agent.required_env) | set(benchmark.required_env))),
            ports=benchmark_ports,
            launch_hints=benchmark_launch_hints,
        )
        pair_recipe = self.find_pair_runtime_recipe(agent.agent_id, benchmark.benchmark_id)
        if pair_recipe is not None:
            recipe = pair_recipe.apply_to(recipe)
        recipe.validate()
        return recipe

    def find_pair_runtime_recipe(
        self,
        agent_id: str,
        benchmark_id: str,
    ) -> PairRuntimeRecipeSpec | None:
        for recipe in self.pair_runtime_recipes:
            if recipe.matches(agent_id, benchmark_id):
                return recipe
        return None

    def expand_matrix(self) -> list[dict[str, Any]]:
        combinations: list[dict[str, Any]] = []
        for seed in self.matrix.seeds:
            for agent in self.agents:
                for benchmark in self.benchmarks:
                    recipe = self.build_runtime_recipe(agent, benchmark)
                    combinations.append(
                        {
                            "agent_id": agent.agent_id,
                            "agent_variant": agent.variant,
                            "model_ref": agent.model_ref,
                            "benchmark_id": benchmark.benchmark_id,
                            "seed": seed,
                            "runtime_recipe": recipe.to_dict(),
                        }
                    )
        return combinations

    @property
    def matrix_cardinality(self) -> int:
        return len(self.matrix.seeds) * len(self.agents) * len(self.benchmarks)

    def _benchmark_runtime_hints(
        self,
        benchmark: BenchmarkSpec,
    ) -> tuple[dict[str, int], dict[str, str]]:
        if not benchmark.options:
            return {}, {}
        ports: dict[str, int] = {}
        launch_hints: dict[str, str] = {
            "benchmark_options_json": json.dumps(benchmark.options, sort_keys=True),
        }
        if benchmark.task_source.path:
            launch_hints["benchmark_task_source_path"] = benchmark.task_source.path
        for key, value in benchmark.options.items():
            if isinstance(value, bool):
                launch_hints.setdefault(key, "true" if value else "false")
                continue
            if isinstance(value, int):
                if key.endswith("_port"):
                    ports[key] = value
                launch_hints.setdefault(key, str(value))
                continue
            if isinstance(value, float):
                launch_hints.setdefault(key, str(value))
                continue
            if isinstance(value, str):
                if value.strip():
                    launch_hints.setdefault(key, value.strip())
                continue
            if isinstance(value, list) and value:
                launch_hints.setdefault(key, json.dumps(value, sort_keys=True))
        return ports, launch_hints

    def normalized_summary(self) -> dict[str, Any]:
        return {
            "project": {
                "name": self.project.name,
                "run_name": self.project.run_name,
                "description": self.project.description,
            },
            "models": [
                {
                    "model_id": model.model_id,
                    "provider": model.provider,
                    "api_style": model.api_style,
                    "modalities": list(model.modalities),
                }
                for model in self.models
            ],
            "agents": [
                {
                    "agent_id": agent.agent_id,
                    "variant": agent.variant,
                    "model_ref": agent.model_ref,
                    "integration_mode": agent.integration_mode.value,
                    "worker_mode": (agent.worker_mode or self.runtime.default_worker_mode).value,
                    "required_modalities": list(agent.required_modalities),
                    "supported_backends": list(agent.supported_backends),
                    "supported_model_protocols": list(agent.supported_model_protocols),
                }
                for agent in self.agents
            ],
            "benchmarks": [
                {
                    "benchmark_id": benchmark.benchmark_id,
                    "display_name": benchmark.display_name,
                    "integration_mode": benchmark.integration_mode.value,
                    "task_source_kind": benchmark.task_source.kind.value,
                    "task_source_path": benchmark.task_source.path,
                    "task_source_selector": benchmark.task_source.selector,
                    "task_source_manifest": benchmark.task_source.manifest,
                    "scorer_ref": benchmark.scorer_ref,
                    "reset_policy": benchmark.reset_policy,
                    "reset_requirements": dict(benchmark.reset_requirements),
                    "device_backend": benchmark.device_backend,
                    "required_env": list(benchmark.required_env),
                    "supported_agent_ids": list(benchmark.supported_agent_ids),
                    "options": dict(benchmark.options),
                }
                for benchmark in self.benchmarks
            ],
            "devices": {
                "default_profile": self.devices.default_profile,
                "control_backend": self.devices.control_backend,
                "device_mode": self.devices.device_mode.value,
                "adb_serials": list(self.devices.adb_serials),
                "avd_names": list(self.devices.avd_names),
                "profiles": [profile.profile_id for profile in self.devices.emulator_profiles],
            },
            "pair_runtime_recipes": [
                {
                    "recipe_id": recipe.recipe_id,
                    "agent_id": recipe.agent_id,
                    "benchmark_id": recipe.benchmark_id,
                    "bridge_id": recipe.bridge_id,
                    "requires_bridge": recipe.requires_bridge,
                    "worker_mode": None if recipe.worker_mode is None else recipe.worker_mode.value,
                    "control_backend": recipe.control_backend,
                }
                for recipe in self.pair_runtime_recipes
            ],
            "runtime": {
                "batch_size": self.runtime.batch_size,
                "default_worker_mode": self.runtime.default_worker_mode.value,
                "observation_mode": self.runtime.observation_mode.value,
                "env_isolation": self.runtime.env_isolation.value,
                "max_steps": self.runtime.max_steps,
                "timeout_sec": self.runtime.timeout_sec,
            },
            "policies": {
                "reset": self.reset.name,
                "artifact_level": self.artifacts.level.value,
                "retry_on": list(self.retries.retry_on),
            },
            "matrix": {
                "expand": self.matrix.expand,
                "seeds": list(self.matrix.seeds),
                "trial_blueprints": self.matrix_cardinality,
                "pair_runtime_recipe_count": len(self.pair_runtime_recipes),
            },
        }
