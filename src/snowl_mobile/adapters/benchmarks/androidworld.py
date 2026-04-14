from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from snowl_mobile.adapters.base import AdapterMetadata
from snowl_mobile.adapters.benchmarks.base import (
    BaseBenchmarkAdapter,
    BenchmarkProbeRequest,
    BenchmarkProbeResult,
)
from snowl_mobile.core.benchmark_spec import BenchmarkSpec, MetricSchemaSpec, TaskSourceSpec
from snowl_mobile.core.enums import IntegrationMode, TaskSourceKind
from snowl_mobile.core.errors import IntegrationError
from snowl_mobile.core.run_context import RunContext
from snowl_mobile.core.trial_context import TrialContext
from snowl_mobile.devices.android_ports import resolve_androidworld_console_port
from snowl_mobile.integration.benchmark_contract import (
    BenchmarkAdapterContract,
    BenchmarkContractValidator,
    NativeMetricMapping,
)
from snowl_mobile.integration.references import resolve_repo_under_references
from snowl_mobile.scoring.score_bundle import ScoreBundle
from snowl_mobile.schemas.observation import ObservationBundle


_REPO_ENV_VAR = "ANDROID_WORLD_HOME"
_DEFAULT_REPO_CANDIDATES = (
    Path("references/benchmarks/android_world"),
    Path("references/benchmarks/AndroidWorld"),
)
_REGISTRY_RELATIVE_PATH = "android_world/registry.py"
_TASK_METADATA_RELATIVE_PATH = "android_world/task_metadata.json"
_MINIWOB_REGISTRY_RELATIVE_PATH = "android_world/task_evals/miniwob/miniwob_registry.py"
_INFO_RETRIEVAL_PROTO_RELATIVE_PATH = (
    "android_world/task_evals/information_retrieval/proto/tasks.textproto"
)
_SUPPORTED_SUITE_FAMILIES = (
    "android_world",
    "android",
    "miniwob",
    "miniwob_subset",
    "information_retrieval",
)


def _extract_top_level_textproto_task_names(content: str) -> tuple[str, ...]:
    names: list[str] = []
    in_task = False
    depth = 0
    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        opens = raw_line.count("{")
        closes = raw_line.count("}")
        if stripped.startswith("tasks {"):
            in_task = True
            depth = 1
            continue
        if not in_task:
            continue
        if depth == 1 and stripped.startswith('name: "'):
            names.append(stripped.split('"', 2)[1])
        depth += opens - closes
        if depth <= 0:
            in_task = False
            depth = 0
    return tuple(sorted(dict.fromkeys(name for name in names if name)))


@dataclass(frozen=True, slots=True)
class AndroidWorldTask:
    suite_family: str
    task_name: str
    instruction: str
    combination_index: int
    n_task_combinations: int
    task_instance_seed: int
    task_template: str = ""
    difficulty: str = ""
    optimal_steps: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def task_id(self) -> str:
        base = f"{self.suite_family}:{self.task_name}"
        if self.n_task_combinations <= 1:
            return base
        return f"{base}:combination-{self.combination_index:04d}"

    def to_plan_payload(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "instruction": self.instruction,
            "suite_family": self.suite_family,
            "task_name": self.task_name,
            "task_template": self.task_template,
            "difficulty": self.difficulty,
            "optimal_steps": self.optimal_steps,
            "tags": list(self.tags),
            "combination_index": self.combination_index,
            "n_task_combinations": self.n_task_combinations,
            "task_instance_seed": self.task_instance_seed,
        }


@dataclass(frozen=True, slots=True)
class AndroidWorldBenchmarkOptions:
    suite_family: str = "android_world"
    tasks: tuple[str, ...] = ()
    n_task_combinations: int = 1
    task_random_seed: int = 30
    fixed_task_seed: bool = False
    perform_emulator_setup: bool = False
    checkpoint_dir: str = ""
    output_path: str = ""
    adb_path: str = ""
    console_port: int = 5554
    grpc_port: int = 8554
    freeze_datetime: bool = True
    python_executable: str = ""
    requirements_file: str = ""
    worker_env_name: str = ""

    @classmethod
    def from_benchmark_spec(
        cls, benchmark: BenchmarkSpec | None
    ) -> "AndroidWorldBenchmarkOptions":
        raw = {} if benchmark is None else benchmark.options
        return cls.from_mapping(raw)

    @classmethod
    def from_mapping(cls, raw: object) -> "AndroidWorldBenchmarkOptions":
        if not isinstance(raw, dict):
            raise IntegrationError("AndroidWorld benchmark options must be a mapping.")
        suite_family = cls._expect_string(raw.get("suite_family", "android_world"), "suite_family")
        if suite_family not in _SUPPORTED_SUITE_FAMILIES:
            allowed = ", ".join(_SUPPORTED_SUITE_FAMILIES)
            raise IntegrationError(
                f"AndroidWorld suite_family '{suite_family}' is not supported. Allowed: {allowed}."
            )
        return cls(
            suite_family=suite_family,
            tasks=cls._parse_tasks(raw.get("tasks", [])),
            n_task_combinations=cls._expect_int(
                raw.get("n_task_combinations", 1),
                "n_task_combinations",
                minimum=1,
            ),
            task_random_seed=cls._expect_int(raw.get("task_random_seed", 30), "task_random_seed"),
            fixed_task_seed=cls._expect_bool(raw.get("fixed_task_seed", False), "fixed_task_seed"),
            perform_emulator_setup=cls._expect_bool(
                raw.get("perform_emulator_setup", False),
                "perform_emulator_setup",
            ),
            checkpoint_dir=cls._expect_optional_string(raw.get("checkpoint_dir", ""), "checkpoint_dir"),
            output_path=cls._expect_optional_string(raw.get("output_path", ""), "output_path"),
            adb_path=cls._expect_optional_string(raw.get("adb_path", ""), "adb_path"),
            console_port=cls._expect_int(raw.get("console_port", 5554), "console_port", minimum=1),
            grpc_port=cls._expect_int(raw.get("grpc_port", 8554), "grpc_port", minimum=1),
            freeze_datetime=cls._expect_bool(raw.get("freeze_datetime", True), "freeze_datetime"),
            python_executable=cls._expect_optional_string(
                raw.get("python_executable", ""),
                "python_executable",
            ),
            requirements_file=cls._expect_optional_string(
                raw.get("requirements_file", ""),
                "requirements_file",
            ),
            worker_env_name=cls._expect_optional_string(
                raw.get("worker_env_name", ""),
                "worker_env_name",
            ),
        )

    @staticmethod
    def _expect_string(value: object, label: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise IntegrationError(f"AndroidWorld option '{label}' must be a non-empty string.")
        return value.strip()

    @staticmethod
    def _expect_optional_string(value: object, label: str) -> str:
        if not isinstance(value, str):
            raise IntegrationError(f"AndroidWorld option '{label}' must be a string.")
        return value.strip()

    @staticmethod
    def _expect_bool(value: object, label: str) -> bool:
        if not isinstance(value, bool):
            raise IntegrationError(f"AndroidWorld option '{label}' must be a boolean.")
        return value

    @staticmethod
    def _expect_int(value: object, label: str, minimum: int | None = None) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise IntegrationError(f"AndroidWorld option '{label}' must be an integer.")
        if minimum is not None and value < minimum:
            raise IntegrationError(f"AndroidWorld option '{label}' must be >= {minimum}.")
        return value

    @classmethod
    def _parse_tasks(cls, value: object) -> tuple[str, ...]:
        if value in (None, ""):
            return ()
        if isinstance(value, str):
            normalized = [item.strip() for item in value.split(",") if item.strip()]
            return tuple(normalized)
        if not isinstance(value, list):
            raise IntegrationError("AndroidWorld option 'tasks' must be a list of strings.")
        normalized: list[str] = []
        for item in value:
            normalized.append(cls._expect_string(item, "tasks[]"))
        return tuple(normalized)


def resolve_androidworld_repo_path(repo_path: Path | None = None) -> Path:
    return resolve_repo_under_references(
        integration_name="AndroidWorld repository",
        default_candidates=_DEFAULT_REPO_CANDIDATES,
        requested_path=repo_path,
        exists_predicate=lambda candidate: (candidate / _REGISTRY_RELATIVE_PATH).exists(),
        expectation_description=f"Expected to find '{_REGISTRY_RELATIVE_PATH}'",
    )


def build_androidworld_contract() -> BenchmarkAdapterContract:
    return BenchmarkContractValidator().validate(
        BenchmarkAdapterContract(
            task_discovery_entry="android_world/registry.py::TaskRegistry.get_registry + android_world/suite_utils.py::create_suite",
            environment_init_entry="android_world/env/env_launcher.py::load_and_setup_env",
            pre_task_setup_entry="android_world/task_evals/task_eval.py::TaskEval.initialize_task",
            reset_entry="android_world/env/interface.py::AsyncEnv.reset",
            run_entry="run.py::_main / minimal_task_runner.py::_main",
            score_capture_entry="android_world/task_evals/task_eval.py::TaskEval.is_successful + android_world/suite_utils.py::process_episodes",
            cleanup_entry="android_world/task_evals/task_eval.py::TaskEval.tear_down",
            observation_form="android_env state + screenshot + accessibility tree",
            action_execution_path="android_world/env/interface.py::AsyncEnv.execute_action + android_world/env/json_action.py",
            raw_artifact_capture_points=(
                "android_world/checkpointer.py::IncrementalCheckpointer",
                "android_world/episode_runner.py::run_episode",
            ),
            native_metric_mappings=(
                NativeMetricMapping(
                    native_metric="task_success",
                    platform_metric="task_success",
                    rationale="Preserve AndroidWorld task-level success as the platform primary metric.",
                ),
                NativeMetricMapping(
                    native_metric="episode_length",
                    platform_metric="episode_length",
                    rationale="Keep benchmark-native step count for later reporting and debugging.",
                ),
                NativeMetricMapping(
                    native_metric="env_reward",
                    platform_metric="reward",
                    rationale="Keep environment-side reward signals available for future bridge reconciliation.",
                ),
            ),
        )
    )


class AndroidWorldBenchmarkAdapter(BaseBenchmarkAdapter):
    def __init__(self) -> None:
        self._probe_cache: dict[str, BenchmarkProbeResult] = {}

    @property
    def adapter_id(self) -> str:
        return "androidworld"

    def describe(self) -> BenchmarkSpec:
        return BenchmarkSpec(
            benchmark_id=self.adapter_id,
            display_name="AndroidWorld",
            integration_mode=IntegrationMode.HYBRID,
            task_source=TaskSourceSpec(
                kind=TaskSourceKind.REFERENCE_REPO,
                path="references/benchmarks/android_world",
                selector="all",
                manifest=_REGISTRY_RELATIVE_PATH,
            ),
            metric_schema=MetricSchemaSpec(
                primary_metric="task_success",
                native_metrics=(
                    "task_success",
                    "episode_length",
                    "env_reward",
                    "num_complete_trials",
                    "mean_success_rate",
                ),
            ),
            scorer_ref="androidworld.native",
            reset_policy="benchmark_native_reset",
            reset_requirements={
                "requires_existing_emulator": True,
                "requires_grpc_emulator": True,
                "upstream_setup_entry": "android_world/env/env_launcher.py::load_and_setup_env",
                "upstream_reset_entry": "android_world/env/interface.py::AsyncEnv.reset",
            },
            device_backend="adb",
            required_env=("ANDROID_SDK_ROOT", "ANDROID_WORLD_HOME"),
            supported_agent_ids=("dummy_text_agent", "dummy_vision_agent"),
            options={
                "suite_family": "android_world",
                "tasks": [],
                "n_task_combinations": 1,
                "task_random_seed": 30,
                "fixed_task_seed": False,
                "perform_emulator_setup": False,
                "checkpoint_dir": "",
                "output_path": "",
                "adb_path": "",
                "console_port": 5554,
                "grpc_port": 8554,
                "freeze_datetime": True,
                "python_executable": "",
                "requirements_file": "references/benchmarks/android_world/requirements.txt",
                "worker_env_name": "androidworld",
            },
        )

    def metadata(self) -> AdapterMetadata:
        spec = self.describe()
        return AdapterMetadata(
            adapter_id=spec.benchmark_id,
            kind=self.kind,
            integration_mode=spec.integration_mode.value,
            supported_backends=(spec.device_backend,),
            required_env=spec.required_env,
            supported_benchmarks=(spec.benchmark_id,),
            extra={
                "scorer_ref": spec.scorer_ref,
                "reset_policy": spec.reset_policy,
                "task_source_kind": spec.task_source.kind.value,
                "supported_suite_families": list(_SUPPORTED_SUITE_FAMILIES),
                "requires_grpc_emulator": True,
                "first_real_pair_status": "open_autoglm_minimal_real_pair",
                "benchmark_side_commands": ["benchmark-setup", "benchmark-run"],
            },
        )

    def list_tasks(self, project_ctx: RunContext) -> list[object]:
        benchmark_spec = next(
            (
                benchmark
                for benchmark in project_ctx.project_snapshot.benchmarks
                if benchmark.benchmark_id == self.adapter_id
            ),
            None,
        )
        options = AndroidWorldBenchmarkOptions.from_benchmark_spec(benchmark_spec)
        repo_path = resolve_androidworld_repo_path(
            None if benchmark_spec is None else Path(benchmark_spec.task_source.path)
        )
        available_tasks = self._load_family_task_names(repo_path, options.suite_family)
        selected_names = self._select_task_names(available_tasks, options.tasks, options.suite_family)
        metadata = self._load_task_metadata(repo_path)
        planned_tasks: list[dict[str, object]] = []
        for task_name in selected_names:
            task_metadata = metadata.get(task_name, {})
            for combination_index in range(1, options.n_task_combinations + 1):
                task_instance_seed = self._build_task_instance_seed(
                    task_name=task_name,
                    task_random_seed=options.task_random_seed,
                    combination_index=combination_index,
                    fixed_task_seed=options.fixed_task_seed,
                )
                instruction = self._build_instruction(
                    task_name,
                    options.suite_family,
                    task_metadata,
                    repo_path=repo_path,
                    options=options,
                    task_instance_seed=task_instance_seed,
                )
                planned_tasks.append(
                    AndroidWorldTask(
                        suite_family=options.suite_family,
                        task_name=task_name,
                        instruction=instruction,
                        combination_index=combination_index,
                        n_task_combinations=options.n_task_combinations,
                        task_instance_seed=task_instance_seed,
                        task_template=str(task_metadata.get("task_template", "")),
                        difficulty=str(task_metadata.get("difficulty", "")),
                        optimal_steps=str(task_metadata.get("optimal_steps", "")),
                        tags=tuple(str(tag) for tag in task_metadata.get("tags", [])),
                    ).to_plan_payload()
                )
        return planned_tasks

    def prepare_trial(self, ctx: TrialContext) -> None:
        if not ctx.trial_spec.task_id:
            raise IntegrationError("AndroidWorld trial requires a non-empty task_id.")
        self._probe_cache.pop(ctx.trial_spec.trial_id, None)

    def seed_environment(self, ctx: TrialContext) -> None:
        self._ensure_probe_cache(ctx)

    def get_initial_observation(self, ctx: TrialContext) -> ObservationBundle:
        return self._ensure_probe_cache(ctx).observation

    def cleanup_trial(self, ctx: TrialContext) -> None:
        self._probe_cache.pop(ctx.trial_spec.trial_id, None)

    def capture_raw_artifacts(self, ctx: TrialContext) -> dict[str, str]:
        return dict(self._ensure_probe_cache(ctx).raw_artifacts)

    def map_native_metrics(self, native_metrics: dict[str, object]) -> dict[str, object]:
        mapped = dict(native_metrics)
        if "env_reward" in native_metrics and "reward" not in mapped:
            mapped["reward"] = native_metrics["env_reward"]
        return mapped

    def build_probe_request(
        self,
        ctx: TrialContext,
        *,
        output_dir: Path,
        operation: str,
        task_payload: dict[str, object],
        task_instruction: str,
        emulator_instance: object | None,
        mock_mode: bool,
    ) -> BenchmarkProbeRequest:
        if not operation.strip():
            raise IntegrationError("AndroidWorld benchmark probe operation must not be empty.")
        resolved_payload = dict(task_payload) if task_payload else self._task_payload_from_trial_context(ctx)
        return BenchmarkProbeRequest(
            trial_context=ctx,
            output_dir=output_dir,
            operation=operation.strip(),
            task_payload=resolved_payload,
            task_instruction=task_instruction or str(resolved_payload.get("instruction", "") or ""),
            emulator_instance=emulator_instance,
            mock_mode=mock_mode,
        )

    def run_benchmark_probe(self, request: BenchmarkProbeRequest) -> BenchmarkProbeResult:
        request.output_dir.mkdir(parents=True, exist_ok=True)
        raw_dir = request.output_dir / "raw" / "androidworld"
        raw_dir.mkdir(parents=True, exist_ok=True)
        request_path = raw_dir / f"{request.operation}.request.json"

        if request.mock_mode:
            result = self._run_mock_probe(request=request, raw_dir=raw_dir)
            self._probe_cache[request.trial_context.trial_spec.trial_id] = result
            return result

        options = self._options_from_trial_context(request.trial_context)
        repo_path = self._repo_path_from_trial_context(request.trial_context)
        python_executable = (
            options.python_executable
            or os.environ.get("ANDROID_WORLD_PYTHON", "").strip()
            or sys.executable
        )
        request_payload = {
            "trial_id": request.trial_context.trial_spec.trial_id,
            "task_id": request.trial_context.trial_spec.task_id,
            "output_dir": request.output_dir.as_posix(),
            "operation": request.operation,
            "task_payload": request.task_payload,
            "task_instruction": request.task_instruction,
            "benchmark_options": {
                **asdict(options),
                "adb_path": options.adb_path or os.environ.get("ANDROID_WORLD_ADB_PATH", "adb"),
            },
            "repo_path": repo_path.as_posix(),
            "console_port": self._resolve_console_port(request, options),
            "grpc_port": getattr(request.emulator_instance, "grpc_port", None),
        }
        if getattr(request.emulator_instance, "adb_serial", None):
            request_payload["adb_serial"] = getattr(request.emulator_instance, "adb_serial")
        if getattr(request.emulator_instance, "grpc_port", None):
            request_payload["grpc_port"] = getattr(request.emulator_instance, "grpc_port")
        if getattr(request.emulator_instance, "adb_serial", None) and not request_payload.get("console_port"):
            request_payload["console_port"] = options.console_port
        request_path.write_text(json.dumps(request_payload, indent=2, sort_keys=True), encoding="utf-8")

        result_path = raw_dir / f"{request.operation}.result.json"
        stdout_path = raw_dir / f"{request.operation}.stdout.txt"
        stderr_path = raw_dir / f"{request.operation}.stderr.txt"
        command = [
            python_executable,
            "-m",
            "snowl_mobile.adapters.benchmarks.androidworld_runtime",
            request_path.as_posix(),
            result_path.as_posix(),
        ]
        env = os.environ.copy()
        src_root = Path(__file__).resolve().parents[3]
        pythonpath_entries = [src_root.as_posix(), repo_path.as_posix()]
        if env.get("PYTHONPATH"):
            pythonpath_entries.append(env["PYTHONPATH"])
        env["PYTHONPATH"] = os.pathsep.join(pythonpath_entries)
        env["ANDROID_WORLD_HOME"] = repo_path.as_posix()
        completed = subprocess.run(
            command,
            cwd=Path(__file__).resolve().parents[4],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        if completed.returncode != 0:
            failure_path = raw_dir / "failure.json"
            existing_failure: dict[str, Any] = {}
            if failure_path.exists():
                try:
                    parsed_failure = json.loads(failure_path.read_text(encoding="utf-8"))
                except Exception:
                    parsed_failure = None
                if isinstance(parsed_failure, dict):
                    existing_failure = parsed_failure
            failure_payload = {
                **existing_failure,
                "command": command,
                "python_executable": python_executable,
                "requirements_file": options.requirements_file,
                "returncode": completed.returncode,
                "stdout_path": stdout_path.relative_to(request.output_dir).as_posix(),
                "stderr_path": stderr_path.relative_to(request.output_dir).as_posix(),
            }
            failure_path.write_text(
                json.dumps(failure_payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            failure_detail = ""
            error_message = existing_failure.get("error_message")
            if isinstance(error_message, str) and error_message.strip():
                failure_detail = f" Runtime helper reported: {error_message.strip()}"
                if "RUNTIME_IMPORT_ERROR" in error_message:
                    requirements_hint = (
                        options.requirements_file
                        or "references/benchmarks/android_world/requirements.txt"
                    )
                    failure_detail += (
                        f" The probe used interpreter '{python_executable}'. "
                        "Set `ANDROID_WORLD_PYTHON` or "
                        "`benchmarks[*].options.python_executable` to a dedicated AndroidWorld "
                        f"environment installed with `{requirements_hint}`."
                    )
            raise IntegrationError(
                "AndroidWorld benchmark probe failed. "
                f"See {stderr_path.relative_to(request.output_dir).as_posix()} and "
                f"{failure_path.relative_to(request.output_dir).as_posix()} for details."
                f"{failure_detail}"
            )
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise IntegrationError("AndroidWorld runtime helper returned a non-object result payload.")
        raw_artifacts = {
            **{
                "androidworld_request": request_path.relative_to(request.output_dir).as_posix(),
                "androidworld_stdout": stdout_path.relative_to(request.output_dir).as_posix(),
                "androidworld_stderr": stderr_path.relative_to(request.output_dir).as_posix(),
                "androidworld_result": result_path.relative_to(request.output_dir).as_posix(),
            },
            **{
                str(key): str(value)
                for key, value in dict(payload.get("raw_artifacts", {})).items()
            },
        }
        result = BenchmarkProbeResult(
            observation=ObservationBundle(**dict(payload.get("observation", {}))),
            score_bundle=ScoreBundle(
                native_metrics=dict(payload.get("native_metrics", {})),
                primary_metric=payload.get("primary_metric"),
                platform_metrics=dict(payload.get("platform_metrics", {})),
                notes=list(payload.get("notes", [])),
            ),
            raw_artifacts=raw_artifacts,
            notes=tuple(payload.get("notes", [])),
        )
        self._probe_cache[request.trial_context.trial_spec.trial_id] = result
        return result

    def _resolve_console_port(
        self,
        request: BenchmarkProbeRequest,
        options: AndroidWorldBenchmarkOptions,
    ) -> int:
        emulator_instance = request.emulator_instance
        if emulator_instance is None:
            return options.console_port
        return resolve_androidworld_console_port(
            emulator_instance=emulator_instance,
            benchmark_options={"console_port": options.console_port},
        )

    def _ensure_probe_cache(self, ctx: TrialContext) -> BenchmarkProbeResult:
        cached = self._probe_cache.get(ctx.trial_spec.trial_id)
        if cached is not None:
            return cached
        if ctx.trial_output_dir is None:
            raise IntegrationError(
                "AndroidWorld benchmark bootstrap requires TrialContext.trial_output_dir."
            )
        result = self.run_benchmark_probe(
            self.build_probe_request(
                ctx,
                output_dir=ctx.trial_output_dir,
                operation="bootstrap",
                task_payload=self._task_payload_from_trial_context(ctx),
                task_instruction="",
                emulator_instance=None,
                mock_mode=False,
            )
        )
        self._probe_cache[ctx.trial_spec.trial_id] = result
        return result

    def _options_from_trial_context(self, ctx: TrialContext) -> AndroidWorldBenchmarkOptions:
        raw = ctx.trial_spec.runtime_recipe.launch_hints.get("benchmark_options_json", "")
        if not raw:
            return AndroidWorldBenchmarkOptions.from_mapping(self.describe().options)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as error:
            raise IntegrationError("AndroidWorld benchmark_options_json is not valid JSON.") from error
        return AndroidWorldBenchmarkOptions.from_mapping(payload)

    def _repo_path_from_trial_context(self, ctx: TrialContext) -> Path:
        raw = ctx.trial_spec.runtime_recipe.launch_hints.get("benchmark_task_source_path", "")
        candidate = Path(raw) if raw else Path(self.describe().task_source.path)
        return resolve_androidworld_repo_path(candidate)

    def _task_payload_from_trial_context(self, ctx: TrialContext) -> dict[str, object]:
        options = self._options_from_trial_context(ctx)
        task_id = ctx.trial_spec.task_id
        parts = [part for part in task_id.split(":") if part]
        if len(parts) < 2:
            raise IntegrationError(f"Unable to reconstruct AndroidWorld task payload from '{task_id}'.")
        suite_family = parts[0]
        task_name = parts[1]
        combination_index = 1
        if len(parts) >= 3 and parts[2].startswith("combination-"):
            suffix = parts[2].split("-", maxsplit=1)[-1]
            combination_index = int(suffix)
        task_metadata = self._load_task_metadata(self._repo_path_from_trial_context(ctx)).get(task_name, {})
        return AndroidWorldTask(
            suite_family=suite_family,
            task_name=task_name,
            instruction=self._build_instruction(task_name, suite_family, task_metadata),
            combination_index=combination_index,
            n_task_combinations=max(options.n_task_combinations, combination_index),
            task_instance_seed=self._build_task_instance_seed(
                task_name=task_name,
                task_random_seed=options.task_random_seed,
                combination_index=combination_index,
                fixed_task_seed=options.fixed_task_seed,
            ),
            task_template=str(task_metadata.get("task_template", "")),
            difficulty=str(task_metadata.get("difficulty", "")),
            optimal_steps=str(task_metadata.get("optimal_steps", "")),
            tags=tuple(str(tag) for tag in task_metadata.get("tags", [])),
        ).to_plan_payload()

    def _run_mock_probe(
        self,
        *,
        request: BenchmarkProbeRequest,
        raw_dir: Path,
    ) -> BenchmarkProbeResult:
        screenshot_path = raw_dir / "mock_observation.png"
        ui_tree_path = raw_dir / "mock_ui_tree.json"
        request_path = raw_dir / f"{request.operation}.request.json"
        result_path = raw_dir / f"{request.operation}.result.json"
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        screenshot_path.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
            b"\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04\x00\x01"
            b"\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        ui_tree_path.write_text(
            json.dumps(
                {
                    "ui_element_count": 1,
                    "elements": [
                        {
                            "text": "Mock AndroidWorld UI element",
                            "resource_id": "snowl-mobile.mock",
                        }
                    ],
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        request_path.write_text(
            json.dumps(
                {
                    "task_id": request.trial_context.trial_spec.task_id,
                    "operation": request.operation,
                    "task_payload": request.task_payload,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        payload = {
            "observation": {
                "timestamp": None,
                "screenshot_path": screenshot_path.relative_to(request.output_dir).as_posix(),
                "xml_path": None,
                "ui_tree_json_path": ui_tree_path.relative_to(request.output_dir).as_posix(),
                "parsed_text": "Mock AndroidWorld observation",
                "activity": "com.example.mock/.MainActivity",
                "package_name": "com.example.mock",
                "screen_size": "1080x2400",
                "orientation": "portrait",
                "source_backend": "androidworld",
                "extra": {
                    "mock_mode": True,
                    "task_name": str(request.task_payload.get("task_name", "")),
                },
            },
            "native_metrics": {
                "task_success": 0.0,
                "episode_length": 0,
                "env_reward": 0.0,
            },
            "primary_metric": 0.0,
            "platform_metrics": {
                "benchmark_operation": request.operation,
                "suite_family": str(request.task_payload.get("suite_family", "android")),
                "task_name": str(request.task_payload.get("task_name", "")),
                "mock_mode": True,
            },
            "raw_artifacts": {
                "androidworld_mock_ui_tree": ui_tree_path.relative_to(request.output_dir).as_posix(),
                "androidworld_mock_screenshot": screenshot_path.relative_to(request.output_dir).as_posix(),
            },
            "notes": [
                "AndroidWorld benchmark probe executed in fake-device mode.",
                "No external agent actions were executed, so task_success remains 0 until a pair bridge is added.",
            ],
        }
        result_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return BenchmarkProbeResult(
            observation=ObservationBundle(**dict(payload["observation"])),
            score_bundle=ScoreBundle(
                native_metrics=dict(payload["native_metrics"]),
                primary_metric=payload["primary_metric"],
                platform_metrics=dict(payload["platform_metrics"]),
                notes=list(payload["notes"]),
            ),
            raw_artifacts={
                "androidworld_request": request_path.relative_to(request.output_dir).as_posix(),
                "androidworld_result": result_path.relative_to(request.output_dir).as_posix(),
                **dict(payload["raw_artifacts"]),
            },
            notes=tuple(payload["notes"]),
        )

    def _load_family_task_names(self, repo_path: Path, suite_family: str) -> tuple[str, ...]:
        android_tasks = self._extract_android_task_names(repo_path)
        if suite_family == "android":
            return android_tasks
        if suite_family == "information_retrieval":
            return self._extract_information_retrieval_task_names(repo_path)
        if suite_family == "android_world":
            return tuple(
                sorted(
                    {
                        *android_tasks,
                        *self._extract_information_retrieval_task_names(repo_path),
                    }
                )
            )
        if suite_family == "miniwob":
            return self._extract_miniwob_task_names(repo_path, subset=False)
        if suite_family == "miniwob_subset":
            return self._extract_miniwob_task_names(repo_path, subset=True)
        raise IntegrationError(f"Unsupported AndroidWorld suite family '{suite_family}'.")

    def _select_task_names(
        self,
        available_tasks: tuple[str, ...],
        requested_tasks: tuple[str, ...],
        suite_family: str,
    ) -> tuple[str, ...]:
        if not requested_tasks:
            return available_tasks
        available = set(available_tasks)
        missing = sorted(task_name for task_name in requested_tasks if task_name not in available)
        if missing:
            joined = ", ".join(missing)
            raise IntegrationError(
                f"AndroidWorld tasks not found in suite_family '{suite_family}': {joined}."
            )
        return tuple(task_name for task_name in available_tasks if task_name in requested_tasks)

    def _extract_android_task_names(self, repo_path: Path) -> tuple[str, ...]:
        module = ast.parse((repo_path / _REGISTRY_RELATIVE_PATH).read_text(encoding="utf-8"))
        for node in module.body:
            if not isinstance(node, ast.ClassDef) or node.name != "TaskRegistry":
                continue
            for child in node.body:
                if not isinstance(child, ast.Assign):
                    continue
                if not any(isinstance(target, ast.Name) and target.id == "_TASKS" for target in child.targets):
                    continue
                if not isinstance(child.value, (ast.Tuple, ast.List)):
                    break
                names = [
                    self._extract_attribute_name(element)
                    for element in child.value.elts
                ]
                return tuple(sorted(name for name in names if name))
        raise IntegrationError("Unable to discover AndroidWorld Android task registry entries.")

    def _extract_miniwob_task_names(self, repo_path: Path, *, subset: bool) -> tuple[str, ...]:
        target_name = "_NAMES_SUBSET" if subset else "_NAMES"
        module = ast.parse((repo_path / _MINIWOB_REGISTRY_RELATIVE_PATH).read_text(encoding="utf-8"))
        for node in module.body:
            if not isinstance(node, ast.Assign):
                continue
            if not any(isinstance(target, ast.Name) and target.id == target_name for target in node.targets):
                continue
            if not isinstance(node.value, (ast.Tuple, ast.List)):
                break
            names: list[str] = []
            for element in node.value.elts:
                if isinstance(element, ast.Constant) and isinstance(element.value, str):
                    names.append(element.value)
            return tuple(sorted(names))
        raise IntegrationError(f"Unable to discover AndroidWorld MiniWoB registry '{target_name}'.")

    def _extract_information_retrieval_task_names(self, repo_path: Path) -> tuple[str, ...]:
        proto_path = repo_path / _INFO_RETRIEVAL_PROTO_RELATIVE_PATH
        content = proto_path.read_text(encoding="utf-8")
        names = _extract_top_level_textproto_task_names(content)
        if not names:
            raise IntegrationError("Unable to discover AndroidWorld information-retrieval tasks.")
        return names

    def _load_task_metadata(self, repo_path: Path) -> dict[str, dict[str, object]]:
        metadata_path = repo_path / _TASK_METADATA_RELATIVE_PATH
        try:
            raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        except OSError as error:
            raise IntegrationError(
                f"Unable to read AndroidWorld task metadata at '{metadata_path.as_posix()}'."
            ) from error
        if not isinstance(raw, list):
            raise IntegrationError("AndroidWorld task metadata must be a list.")
        index: dict[str, dict[str, object]] = {}
        for item in raw:
            if not isinstance(item, dict):
                continue
            task_name = item.get("task_name")
            if isinstance(task_name, str) and task_name.strip():
                index[task_name.strip()] = item
        return index

    def _build_instruction(
        self,
        task_name: str,
        suite_family: str,
        task_metadata: dict[str, object],
        *,
        repo_path: Path | None = None,
        options: AndroidWorldBenchmarkOptions | None = None,
        task_instance_seed: int | None = None,
    ) -> str:
        template = str(task_metadata.get("task_template", "")).strip()
        fallback = template or f"Run AndroidWorld task '{task_name}' from suite family '{suite_family}'."
        if repo_path is None or options is None or task_instance_seed is None:
            return fallback
        materialized = self._materialize_instruction(
            repo_path=repo_path,
            options=options,
            suite_family=suite_family,
            task_name=task_name,
            task_instance_seed=task_instance_seed,
        )
        return materialized or fallback

    def _materialize_instruction(
        self,
        *,
        repo_path: Path,
        options: AndroidWorldBenchmarkOptions,
        suite_family: str,
        task_name: str,
        task_instance_seed: int,
    ) -> str:
        python_executable = (
            options.python_executable
            or os.environ.get("ANDROID_WORLD_PYTHON", "").strip()
            or sys.executable
        )
        if not python_executable:
            return ""
        helper = (
            "import json, random, sys\n"
            "repo_path, suite_family, task_name, seed_value = sys.argv[1:5]\n"
            "sys.path.insert(0, repo_path)\n"
            "from android_world import registry as androidworld_registry\n"
            "seed = int(seed_value)\n"
            "task_type = androidworld_registry.TaskRegistry().get_registry(suite_family)[task_name]\n"
            "random.seed(seed)\n"
            "params = task_type.generate_random_params()\n"
            "if not isinstance(params, dict):\n"
            "    raise TypeError('AndroidWorld task params must be a dict.')\n"
            "params.setdefault('seed', seed)\n"
            "task = task_type(params)\n"
            "print(json.dumps({'goal': str(getattr(task, 'goal', '') or '')}, ensure_ascii=False))\n"
        )
        try:
            completed = subprocess.run(
                [
                    python_executable,
                    "-c",
                    helper,
                    repo_path.as_posix(),
                    suite_family,
                    task_name,
                    str(task_instance_seed),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception:
            return ""
        if completed.returncode != 0:
            return ""
        stdout = completed.stdout.strip()
        if not stdout:
            return ""
        try:
            payload = json.loads(stdout.splitlines()[-1])
        except json.JSONDecodeError:
            return ""
        goal = payload.get("goal")
        if isinstance(goal, str):
            return goal.strip()
        return ""

    def _build_task_instance_seed(
        self,
        *,
        task_name: str,
        task_random_seed: int,
        combination_index: int,
        fixed_task_seed: bool,
    ) -> int:
        seed_index = 0 if fixed_task_seed else combination_index - 1
        unique_seed_str = f"{task_random_seed}_{task_name}_{seed_index}"
        return int(hashlib.sha256(unique_seed_str.encode("utf-8")).hexdigest(), 16) % (2**32)

    @staticmethod
    def _extract_attribute_name(node: ast.expr) -> str:
        if isinstance(node, ast.Attribute):
            return node.attr
        if isinstance(node, ast.Name):
            return node.id
        return ""
