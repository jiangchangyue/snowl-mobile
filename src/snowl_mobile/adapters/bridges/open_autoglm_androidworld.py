from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from snowl_mobile.adapters.agents.open_autoglm import (
    OpenAutoGLMAgentAdapter,
    resolve_open_autoglm_repo_path,
)
from snowl_mobile.adapters.benchmarks.androidworld import (
    AndroidWorldBenchmarkAdapter,
    resolve_androidworld_repo_path,
)
from snowl_mobile.adapters.bridges.base import BaseBridgeAdapter
from snowl_mobile.adapters.bridges.contract import BridgeContract
from snowl_mobile.artifacts.trajectory import (
    TrajectoryArtifacts,
    TrajectoryStep,
    TrajectoryTimestamps,
)
from snowl_mobile.core.errors import DeviceError, IntegrationError
from snowl_mobile.core.enums import IntegrationMode
from snowl_mobile.core.trial_context import TrialContext
from snowl_mobile.devices.emulator_instance import EmulatorInstance
from snowl_mobile.models.model_spec import ModelSpec
from snowl_mobile.schemas.action import ActionRecord
from snowl_mobile.schemas.observation import ObservationBundle
from snowl_mobile.scoring.score_bundle import ScoreBundle


def _utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _relative_to(path_value: str | Path | None, *, root: Path) -> str | None:
    if not path_value:
        return None
    candidate = Path(path_value)
    try:
        return candidate.relative_to(root).as_posix()
    except Exception:
        return str(path_value)


@dataclass(frozen=True, slots=True)
class OpenAutoGLMAndroidWorldRunRequest:
    trial_context: TrialContext
    output_dir: Path
    emulator_instance: EmulatorInstance
    model_spec: ModelSpec
    task_payload: dict[str, object]
    task_instruction: str
    mock_mode: bool = False


@dataclass(frozen=True, slots=True)
class OpenAutoGLMAndroidWorldRunResult:
    score_bundle: ScoreBundle
    trajectory_steps: tuple[TrajectoryStep, ...]
    raw_artifacts: dict[str, str]
    platform_metrics: dict[str, object]
    notes: tuple[str, ...] = ()


class OpenAutoGLMAndroidWorldBridgeAdapter(BaseBridgeAdapter):
    @property
    def adapter_id(self) -> str:
        return "open_autoglm__androidworld"

    @property
    def agent_id(self) -> str:
        return "open_autoglm"

    @property
    def benchmark_id(self) -> str:
        return "androidworld"

    def describe_bridge(self) -> BridgeContract:
        return BridgeContract(
            bridge_id=self.adapter_id,
            agent_id=self.agent_id,
            benchmark_id=self.benchmark_id,
            integration_mode=IntegrationMode.HYBRID,
            observation_mapping_entry=(
                "AndroidWorld env bootstrap/get_state -> ObservationBundle -> "
                "Open-AutoGLM PhoneAgent task prompt"
            ),
            action_mapping_entry=(
                "Open-AutoGLM do(...) -> platform ActionRecord while first-pass "
                "AndroidWorld execution keeps device control on ADB and benchmark-native scoring on AndroidWorld"
            ),
            run_entry="OpenAutoGLMAndroidWorldBridgeAdapter.run_wrapped_pair",
            environment_handshake_entry=(
                "existing Android emulator lease + AndroidWorld load_and_setup_env + "
                "Open-AutoGLM PhoneAgent step loop"
            ),
            artifact_capture_hooks=(
                "trial/raw/open_autoglm_androidworld/bridge_request.json",
                "trial/raw/open_autoglm_androidworld/bridge_stdout.txt",
                "trial/raw/open_autoglm_androidworld/bridge_stderr.txt",
                "trial/raw/open_autoglm_androidworld/final_result.json",
                "trial/raw/open_autoglm_androidworld/steps/0001.model_response.json",
                "trial/trajectory.json",
            ),
            supported_backends=("adb",),
            required_env=(
                "OPEN_AUTOGLM_HOME",
                "ANDROID_WORLD_HOME",
                "ANDROID_SDK_ROOT",
                "PHONE_AGENT_BASE_URL",
                "PHONE_AGENT_API_KEY",
            ),
            requires_pair_recipe=True,
        )

    def map_observation(self, observation: ObservationBundle) -> ObservationBundle:
        extra = dict(observation.extra)
        extra.setdefault("bridge_id", self.adapter_id)
        extra.setdefault("pair_mode", "open_autoglm_x_androidworld")
        return ObservationBundle(
            timestamp=observation.timestamp,
            screenshot_path=observation.screenshot_path,
            xml_path=observation.xml_path,
            ui_tree_json_path=observation.ui_tree_json_path,
            parsed_text=observation.parsed_text,
            activity=observation.activity,
            package_name=observation.package_name,
            screen_size=observation.screen_size,
            orientation=observation.orientation,
            source_backend=observation.source_backend or "bridge.open_autoglm_androidworld",
            extra=extra,
        )

    def build_run_request(
        self,
        ctx: TrialContext,
        *,
        output_dir: Path,
        emulator_instance: EmulatorInstance,
        model_spec: ModelSpec,
        task_payload: dict[str, object],
        task_instruction: str,
        mock_mode: bool,
    ) -> OpenAutoGLMAndroidWorldRunRequest:
        return OpenAutoGLMAndroidWorldRunRequest(
            trial_context=ctx,
            output_dir=output_dir,
            emulator_instance=emulator_instance,
            model_spec=model_spec,
            task_payload=task_payload,
            task_instruction=task_instruction,
            mock_mode=mock_mode,
        )

    def run_wrapped_pair(
        self,
        request: OpenAutoGLMAndroidWorldRunRequest,
    ) -> OpenAutoGLMAndroidWorldRunResult:
        if request.mock_mode:
            return self._run_mock_pair(request)
        return self._run_real_pair(request)

    def run_trial(self, ctx: TrialContext) -> object:
        raise IntegrationError(
            "This bridge requires a structured run request. Use build_run_request() + run_wrapped_pair()."
        )

    def _run_mock_pair(
        self,
        request: OpenAutoGLMAndroidWorldRunRequest,
    ) -> OpenAutoGLMAndroidWorldRunResult:
        benchmark_adapter = AndroidWorldBenchmarkAdapter()
        agent_adapter = OpenAutoGLMAgentAdapter()
        ctx = request.trial_context
        probe_request = benchmark_adapter.build_probe_request(
            ctx,
            output_dir=request.output_dir,
            operation="bootstrap",
            task_payload=request.task_payload,
            task_instruction=request.task_instruction,
            emulator_instance=request.emulator_instance,
            mock_mode=True,
        )
        probe_result = benchmark_adapter.run_benchmark_probe(probe_request)
        observation = self.map_observation(probe_result.observation)
        agent_request = agent_adapter.build_run_request(
            ctx,
            output_dir=request.output_dir,
            observation=observation,
            task_instruction=request.task_instruction or str(request.task_payload.get("instruction", "")),
            mock_mode=True,
        )
        agent_result = agent_adapter.run_wrapped_agent(agent_request)

        bridge_raw_dir = request.output_dir / "raw" / "open_autoglm_androidworld"
        bridge_raw_dir.mkdir(parents=True, exist_ok=True)
        request_path = bridge_raw_dir / "bridge_request.json"
        result_path = bridge_raw_dir / "final_result.json"
        request_path.write_text(
            json.dumps(self._request_payload(request), indent=2, sort_keys=True),
            encoding="utf-8",
        )

        trajectory_step = self._build_mock_step(
            output_dir=request.output_dir,
            task_instruction=request.task_instruction or str(request.task_payload.get("instruction", "")),
            observation=observation,
            action_record=agent_result.action_record,
            model_response_text_path=_relative_to(agent_result.raw_artifacts.get("raw_text_path"), root=request.output_dir),
            model_response_json_path=_relative_to(agent_result.raw_artifacts.get("raw_json_path"), root=request.output_dir),
            thinking=getattr(agent_result.raw_output, "thinking", None),
            raw_action=getattr(agent_result.raw_output, "action_text", None),
        )
        platform_metrics = {
            **dict(probe_result.score_bundle.platform_metrics),
            **dict(agent_result.platform_metrics),
            "control_backend": "adb",
            "pair_bridge": self.adapter_id,
            "mock_mode": True,
        }
        notes = tuple(
            dict.fromkeys(
                [
                    *list(probe_result.notes),
                    "Open-AutoGLM x AndroidWorld mock bridge path exercised the benchmark bootstrap and agent mock action normalization without real device execution.",
                ]
            )
        )
        score_bundle = ScoreBundle(
            native_metrics=dict(probe_result.score_bundle.native_metrics),
            primary_metric=probe_result.score_bundle.primary_metric,
            platform_metrics=platform_metrics,
            notes=list(notes),
        )
        result_path.write_text(
            json.dumps(
                {
                    "score_bundle": score_bundle.to_dict(),
                    "platform_metrics": platform_metrics,
                    "notes": list(notes),
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        raw_artifacts = {
            "bridge_request": request_path.relative_to(request.output_dir).as_posix(),
            "bridge_result": result_path.relative_to(request.output_dir).as_posix(),
            **{f"androidworld_{key}": value for key, value in probe_result.raw_artifacts.items()},
            **{
                f"open_autoglm_{key}": str(_relative_to(value, root=request.output_dir))
                for key, value in agent_result.raw_artifacts.items()
            },
        }
        return OpenAutoGLMAndroidWorldRunResult(
            score_bundle=score_bundle,
            trajectory_steps=(trajectory_step,),
            raw_artifacts=raw_artifacts,
            platform_metrics=platform_metrics,
            notes=notes,
        )

    def _run_real_pair(
        self,
        request: OpenAutoGLMAndroidWorldRunRequest,
    ) -> OpenAutoGLMAndroidWorldRunResult:
        self._validate_real_env(request)
        request.output_dir.mkdir(parents=True, exist_ok=True)
        bridge_raw_dir = request.output_dir / "raw" / "open_autoglm_androidworld"
        bridge_raw_dir.mkdir(parents=True, exist_ok=True)

        runtime_recipe = request.trial_context.trial_spec.runtime_recipe
        benchmark_options_raw = runtime_recipe.launch_hints.get("benchmark_options_json", "")
        if not benchmark_options_raw:
            raise IntegrationError(
                "AndroidWorld bridge is missing benchmark_options_json in the runtime recipe."
            )
        try:
            benchmark_options = json.loads(benchmark_options_raw)
        except json.JSONDecodeError as error:
            raise IntegrationError("AndroidWorld bridge received invalid benchmark_options_json.") from error
        if not isinstance(benchmark_options, dict):
            raise IntegrationError("AndroidWorld bridge expects benchmark_options_json to decode to an object.")

        open_autoglm_repo = resolve_open_autoglm_repo_path()
        androidworld_repo = resolve_androidworld_repo_path(
            Path(runtime_recipe.launch_hints.get("benchmark_task_source_path", ""))  # type: ignore[arg-type]
            if runtime_recipe.launch_hints.get("benchmark_task_source_path", "")
            else None
        )
        python_executable = (
            str(benchmark_options.get("python_executable", "")).strip()
            or os.environ.get("ANDROID_WORLD_PYTHON", "").strip()
            or sys.executable
        )
        request_payload = self._request_payload(request)
        request_payload.update(
            {
                "benchmark_options": benchmark_options,
                "repo_paths": {
                    "open_autoglm": open_autoglm_repo.as_posix(),
                    "androidworld": androidworld_repo.as_posix(),
                },
                "python_executable": python_executable,
                "device": {
                    "adb_serial": request.emulator_instance.adb_serial,
                    "console_port": runtime_recipe.ports.get("console_port", benchmark_options.get("console_port", 5554)),
                    "grpc_port": request.emulator_instance.grpc_port or runtime_recipe.ports.get(
                        "grpc_port",
                        benchmark_options.get("grpc_port", 8554),
                    ),
                },
                "model": {
                    "model_id": request.model_spec.model_id,
                    "provider": request.model_spec.provider,
                    "api_style": request.model_spec.api_style,
                    "modalities": list(request.model_spec.modalities),
                    "supports_image_input": request.model_spec.supports_image_input,
                },
                "max_steps": request.trial_context.trial_spec.max_steps,
            }
        )

        request_path = bridge_raw_dir / "bridge_request.json"
        result_path = bridge_raw_dir / "final_result.json"
        stdout_path = bridge_raw_dir / "bridge_stdout.txt"
        stderr_path = bridge_raw_dir / "bridge_stderr.txt"
        request_path.write_text(json.dumps(request_payload, indent=2, sort_keys=True), encoding="utf-8")

        command = [
            python_executable,
            "-m",
            "snowl_mobile.adapters.bridges.open_autoglm_androidworld_runtime",
            request_path.as_posix(),
            result_path.as_posix(),
        ]
        env = os.environ.copy()
        src_root = Path(__file__).resolve().parents[3]
        pythonpath_entries = [src_root.as_posix(), open_autoglm_repo.as_posix(), androidworld_repo.as_posix()]
        if env.get("PYTHONPATH"):
            pythonpath_entries.append(env["PYTHONPATH"])
        env["PYTHONPATH"] = os.pathsep.join(pythonpath_entries)
        env.setdefault("OPEN_AUTOGLM_HOME", open_autoglm_repo.as_posix())
        env.setdefault("ANDROID_WORLD_HOME", androidworld_repo.as_posix())
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
            failure_path = bridge_raw_dir / "failure.json"
            failure_detail = self._load_failure_payload(failure_path)
            message = self._format_runtime_failure(
                failure_detail=failure_detail,
                stderr_path=stderr_path,
                request=request,
            )
            raise IntegrationError(message)

        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise IntegrationError(
                "Open-AutoGLM x AndroidWorld bridge returned invalid JSON. "
                f"See {result_path.relative_to(request.output_dir).as_posix()}."
            ) from error
        if not isinstance(payload, dict):
            raise IntegrationError("Open-AutoGLM x AndroidWorld bridge returned a non-object result payload.")

        score_bundle = ScoreBundle(
            native_metrics=dict(payload.get("native_metrics", {})),
            primary_metric=payload.get("primary_metric"),
            platform_metrics=dict(payload.get("platform_metrics", {})),
            notes=list(payload.get("notes", [])),
        )
        trajectory_steps = tuple(
            self._trajectory_step_from_payload(step, output_dir=request.output_dir)
            for step in payload.get("trajectory_steps", [])
            if isinstance(step, dict)
        )
        raw_artifacts = {
            "bridge_request": request_path.relative_to(request.output_dir).as_posix(),
            "bridge_stdout": stdout_path.relative_to(request.output_dir).as_posix(),
            "bridge_stderr": stderr_path.relative_to(request.output_dir).as_posix(),
            "bridge_result": result_path.relative_to(request.output_dir).as_posix(),
            **{
                str(key): str(value)
                for key, value in dict(payload.get("raw_artifacts", {})).items()
            },
        }
        notes = tuple(payload.get("notes", []))
        return OpenAutoGLMAndroidWorldRunResult(
            score_bundle=score_bundle,
            trajectory_steps=trajectory_steps,
            raw_artifacts=raw_artifacts,
            platform_metrics=dict(payload.get("platform_metrics", {})),
            notes=notes,
        )

    def _validate_real_env(
        self,
        request: OpenAutoGLMAndroidWorldRunRequest,
    ) -> None:
        missing = [
            name
            for name in ("PHONE_AGENT_BASE_URL", "PHONE_AGENT_API_KEY")
            if not os.environ.get(name)
        ]
        if missing:
            joined = ", ".join(missing)
            raise IntegrationError(
                "real Open-AutoGLM x AndroidWorld runs require these environment variables: "
                f"{joined}"
            )
        if request.emulator_instance.adb_serial.strip() == "":
            raise DeviceError("no adb serial is attached to the leased emulator instance")
        if request.emulator_instance.grpc_port < 1:
            raise DeviceError(
                "AndroidWorld requires a grpc_port on the leased emulator instance. "
                "Launch the emulator from the CLI with the AndroidWorld `-grpc` flag."
            )
        if "image" not in request.model_spec.modalities or not request.model_spec.supports_image_input:
            raise IntegrationError(
                "Open-AutoGLM requires a model with text+image modalities and image input support."
            )

    def _request_payload(
        self,
        request: OpenAutoGLMAndroidWorldRunRequest,
    ) -> dict[str, object]:
        return {
            "trial_id": request.trial_context.trial_spec.trial_id,
            "task_id": request.trial_context.trial_spec.task_id,
            "task_instruction": request.task_instruction,
            "task_payload": request.task_payload,
            "output_dir": request.output_dir.as_posix(),
            "mock_mode": request.mock_mode,
            "model_id": request.model_spec.model_id,
            "adb_serial": request.emulator_instance.adb_serial,
        }

    def _build_mock_step(
        self,
        *,
        output_dir: Path,
        task_instruction: str,
        observation: ObservationBundle,
        action_record: ActionRecord,
        model_response_text_path: str | None,
        model_response_json_path: str | None,
        thinking: str | None,
        raw_action: str | None,
    ) -> TrajectoryStep:
        persisted_at = _utcnow()
        return TrajectoryStep(
            step_index=1,
            attempt=1,
            status="completed",
            observation=observation,
            action=action_record,
            artifacts=TrajectoryArtifacts(
                screenshot_path=observation.screenshot_path,
                xml_path=observation.xml_path,
                model_response_text_path=model_response_text_path,
                model_response_json_path=model_response_json_path,
            ),
            timestamps=TrajectoryTimestamps(
                observed_at=observation.timestamp or persisted_at,
                action_at=persisted_at,
                persisted_at=persisted_at,
            ),
            task_instruction=task_instruction,
            thought=thinking,
            action_text=raw_action,
            action_input=dict(action_record.parsed_action),
            notes=[
                "Open-AutoGLM x AndroidWorld mock bridge step persisted by the pair-specific bridge.",
            ],
        )

    def _load_failure_payload(self, path: Path) -> dict[str, object]:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _format_runtime_failure(
        self,
        *,
        failure_detail: dict[str, object],
        stderr_path: Path,
        request: OpenAutoGLMAndroidWorldRunRequest,
    ) -> str:
        error_message = str(failure_detail.get("error_message", "") or "").strip()
        lowered = error_message.lower()
        stderr_rel = stderr_path.relative_to(request.output_dir).as_posix()
        if (
            "accessibility forwarder" in lowered
            or "accessibility_forwarder.apk" in lowered
            or "storage.googleapis.com/android_env-tasks" in lowered
            or ("urlopen error" in lowered and "ssl" in lowered)
        ):
            return (
                "AndroidWorld failed while installing or refreshing the accessibility forwarder APK. "
                "If the emulator was prepared before, retry with the same emulator so the already-installed package "
                "can be reused; otherwise allow HTTPS access to storage.googleapis.com or run "
                "`snowl-mobile benchmark-setup ...` once from a network-ready environment. "
                f"See {stderr_rel}."
            )
        if (
            "androidworld_app_install_error:" in lowered
            or "failed to download and install apk" in lowered
            or "storage.googleapis.com/gresearch/android_world" in lowered
        ):
            return (
                "AndroidWorld task-scoped app setup failed while downloading or installing an APK required by "
                "the current task. If the emulator was prepared before, retry with the same emulator so the "
                "already-installed package can be reused; otherwise allow HTTPS access to "
                "storage.googleapis.com/gresearch/android_world or prewarm the emulator with "
                "`snowl-mobile benchmark-setup ...` from a network-ready environment. "
                f"See {stderr_rel}."
            )
        if (
            "model_api_error:" in lowered
            or "openai.apiconnectionerror" in lowered
            or "httpx.connecterror" in lowered
            or "httpcore.connecterror" in lowered
            or "ssl: unexpected_eof_while_reading" in lowered
        ):
            return (
                "Open-AutoGLM could not reach the configured model endpoint while running the AndroidWorld step loop. "
                "Check PHONE_AGENT_BASE_URL, PHONE_AGENT_API_KEY, PHONE_AGENT_MODEL, and any proxy/SSL settings. "
                f"See {stderr_rel}."
            )
        if "model_config_error:" in lowered or "phone_agent_base_url" in lowered or "phone_agent_api_key" in lowered:
            return (
                "Open-AutoGLM x AndroidWorld failed before the first model call because model configuration is missing. "
                "Set PHONE_AGENT_BASE_URL, PHONE_AGENT_API_KEY, and PHONE_AGENT_MODEL, then retry. "
                f"See {stderr_rel}."
            )
        if "runtime_import_error:" in lowered:
            package_hint = self._extract_missing_package_hint(error_message)
            package_detail = f" Missing package hint: {package_hint}." if package_hint else ""
            return (
                "Open-AutoGLM x AndroidWorld worker startup failed because the configured Python interpreter is "
                "missing upstream packages. Point ANDROID_WORLD_PYTHON or benchmark.options.python_executable to "
                "an interpreter with both AndroidWorld and Open-AutoGLM requirements installed."
                f"{package_detail} "
                f"See {stderr_rel}."
            )
        if "androidworld_env_error:" in lowered or "grpc" in lowered:
            return (
                "AndroidWorld could not connect to the emulator runtime. Make sure the AVD is running from the CLI "
                "with a gRPC port, for example `emulator -avd AndroidWorldAvd -no-snapshot -grpc 8554`, and run "
                "`snowl-mobile benchmark-setup ...` once if this is the first boot. Also verify that the AVD is "
                "Android 13 / API 33 as required by the upstream AndroidWorld README. "
                f"See {stderr_rel}."
            )
        if "could not get a11y tree" in lowered:
            return (
                "AndroidWorld accessibility runtime became unavailable while AutoGLM was running the task. "
                "Retry with the same emulator first; if this repeats, restart the AVD and rerun with the same "
                "output directory so successful trials are reused. "
                f"See {stderr_rel}."
            )
        if "failed to resolve task" in lowered:
            return (
                "AndroidWorld task discovery selected a task name that the runtime registry could not resolve. "
                "This is usually caused by stale or over-broad `android_world` task discovery pulling non-task "
                "field names from the information-retrieval textproto. Retry with the updated platform task "
                f"discovery and see {stderr_rel}."
            )
        if "time data" in lowered and "does not match format" in lowered:
            return (
                "AndroidWorld task bootstrap failed while parsing the device time reported by `adb shell date`. "
                "This can happen when gRPC or adb noise is mixed into the shell output; retry with the updated "
                "bridge and the same emulator/output directory. "
                f"See {stderr_rel}."
            )
        if "invalid literal for int()" in lowered and "fd from fork parent still in poll list" in lowered:
            return (
                "AndroidWorld task bootstrap failed while parsing the device time reported by `adb shell date +%s`. "
                "This happens when verbose gRPC logs leak into adb shell output. Retry with the updated bridge and "
                f"see {stderr_rel}."
            )
        if (
            "no such module: fts3" in lowered
            or "no such module: fts4" in lowered
            or "no such table:" in lowered
        ):
            return (
                "AndroidWorld task bootstrap hit an upstream SQLite/database initialization problem while preparing "
                "task-scoped app state. The updated bridge retries missing-table initialization and uses the sqlite3 "
                f"CLI fallback for FTS-backed databases. See {stderr_rel}."
            )
        if "androidworld_task_error:" in lowered and "task scoring failed after execution" in lowered:
            return (
                "AndroidWorld native scoring failed after the agent finished executing the task. This usually means "
                "the upstream scorer expected app-owned state that was missing or not initialized on the emulator. "
                "The updated bridge now retries lightweight app initialization before scoring and records a normal "
                "task failure if the missing-table condition persists. "
                f"See {stderr_rel} and `raw/open_autoglm_androidworld/failure.json`."
            )
        if "does not exist" in lowered and "/data/data/" in lowered and (".db" in lowered or "app_db" in lowered):
            return (
                "AndroidWorld task bootstrap hit an app-owned SQLite/database initialization problem while "
                "preparing task-scoped app state. The updated bridge now re-initializes the owning app when the "
                "database path has not been created yet, and treats a still-missing cleanup DB as empty state "
                "instead of crashing the trial. "
                f"See {stderr_rel} and `raw/open_autoglm_androidworld/failure.json`."
            )
        if (
            ("target text" in lowered and "not found" in lowered)
            or "invalid element index" in lowered
        ):
            return (
                "AndroidWorld task bootstrap failed while the benchmark was preparing first-run app state on the "
                "emulator. This usually comes from flaky onboarding/setup UI during contact or app prepopulation. "
                "The updated bridge now refreshes the env, re-runs task-scoped app setup, and retries bootstrap "
                "once before giving up. "
                f"See {stderr_rel} and `raw/open_autoglm_androidworld/failure.json`."
            )
        if "androidworld_task_error:" in lowered:
            return (
                "AndroidWorld task bootstrap failed after the emulator came up. Check the task subset, first-run "
                "setup state, and raw trial artifacts under `raw/open_autoglm_androidworld/`. "
                f"See {stderr_rel}."
            )
        if "autoglm_bridge_error:" in lowered:
            return (
                "Open-AutoGLM bridge execution failed during the step loop. Check the model response and step console "
                "artifacts under `raw/open_autoglm_androidworld/steps/`. "
                f"See {stderr_rel}."
            )
        return (
            "Open-AutoGLM x AndroidWorld bridge execution failed. "
            f"See {stderr_rel} and `raw/open_autoglm_androidworld/failure.json` for details."
        )

    def _extract_missing_package_hint(self, error_message: str) -> str:
        marker = "Missing package appears to be '"
        if marker not in error_message:
            return ""
        tail = error_message.split(marker, 1)[1]
        return tail.split("'", 1)[0].strip()

    def _trajectory_step_from_payload(
        self,
        payload: dict[str, object],
        *,
        output_dir: Path,
    ) -> TrajectoryStep:
        observation_payload = payload.get("observation", {})
        action_payload = payload.get("action", {})
        artifacts_payload = payload.get("artifacts", {})
        timestamps_payload = payload.get("timestamps", {})
        if not isinstance(observation_payload, dict) or not isinstance(action_payload, dict):
            raise IntegrationError("Bridge trajectory payload is missing observation/action objects.")
        return TrajectoryStep(
            step_index=int(payload.get("step_index", 0)),
            attempt=int(payload.get("attempt", 1)),
            status=str(payload.get("status", "completed")),
            observation=ObservationBundle(
                timestamp=observation_payload.get("timestamp"),
                screenshot_path=_relative_to(observation_payload.get("screenshot_path"), root=output_dir),
                xml_path=_relative_to(observation_payload.get("xml_path"), root=output_dir),
                ui_tree_json_path=_relative_to(observation_payload.get("ui_tree_json_path"), root=output_dir),
                parsed_text=observation_payload.get("parsed_text"),
                activity=observation_payload.get("activity"),
                package_name=observation_payload.get("package_name"),
                screen_size=observation_payload.get("screen_size"),
                orientation=observation_payload.get("orientation"),
                source_backend=observation_payload.get("source_backend"),
                extra=dict(observation_payload.get("extra", {})),
            ),
            action=ActionRecord(
                agent_raw_output=action_payload.get("agent_raw_output"),
                parsed_action=dict(action_payload.get("parsed_action", {})),
                executed_action=dict(action_payload.get("executed_action", {})),
                execution_result=dict(action_payload.get("execution_result", {})),
            ),
            artifacts=TrajectoryArtifacts(
                observation_path=_relative_to(artifacts_payload.get("observation_path"), root=output_dir),
                action_path=_relative_to(artifacts_payload.get("action_path"), root=output_dir),
                screenshot_path=_relative_to(artifacts_payload.get("screenshot_path"), root=output_dir),
                xml_path=_relative_to(artifacts_payload.get("xml_path"), root=output_dir),
                model_response_text_path=_relative_to(
                    artifacts_payload.get("model_response_text_path"),
                    root=output_dir,
                ),
                model_response_json_path=_relative_to(
                    artifacts_payload.get("model_response_json_path"),
                    root=output_dir,
                ),
            ),
            timestamps=TrajectoryTimestamps(
                observed_at=str(timestamps_payload.get("observed_at", _utcnow())),
                action_at=str(timestamps_payload.get("action_at", _utcnow())),
                persisted_at=str(timestamps_payload.get("persisted_at", _utcnow())),
            ),
            task_instruction=payload.get("task_instruction"),
            thought=payload.get("thought"),
            action_text=payload.get("action_text"),
            action_input=dict(payload.get("action_input", {})),
            notes=[str(note) for note in payload.get("notes", []) if str(note).strip()],
        )
