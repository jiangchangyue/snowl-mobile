from __future__ import annotations

import importlib
import json
import logging
import os
import shutil
import time
import traceback
from dataclasses import dataclass
from pathlib import Path

from snowl_mobile.adapters.agents.mobile_agent_v3_5 import (
    MobileAgentV35AgentAdapter,
    build_mobile_agent_v3_5_runtime_env,
    resolve_mobile_agent_v3_5_repo_path,
)
from snowl_mobile.adapters.benchmarks.mobilesafetybench import (
    MobileSafetyBenchBenchmarkAdapter,
    resolve_mobilesafetybench_repo_path,
)
from snowl_mobile.adapters.bridges.contract import BridgeContract
from snowl_mobile.adapters.bridges.open_autoglm_mobilesafetybench import (
    OpenAutoGLMMobileSafetyBenchBridgeAdapter,
)
from snowl_mobile.core.errors import DeviceError, IntegrationError
from snowl_mobile.core.enums import IntegrationMode
from snowl_mobile.core.logging import get_trial_logger
from snowl_mobile.core.trial_context import TrialContext
from snowl_mobile.devices.emulator_instance import EmulatorInstance
from snowl_mobile.models.model_spec import ModelSpec
from snowl_mobile.scoring.score_bundle import ScoreBundle
from snowl_mobile.schemas.observation import ObservationBundle


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MobileAgentV35MobileSafetyBenchRunRequest:
    trial_context: TrialContext
    output_dir: Path
    emulator_instance: EmulatorInstance
    model_spec: ModelSpec
    task_payload: dict[str, object]
    task_instruction: str
    mock_mode: bool = False


@dataclass(frozen=True, slots=True)
class MobileAgentV35MobileSafetyBenchRunResult:
    score_bundle: ScoreBundle
    trajectory_steps: tuple[object, ...]
    raw_artifacts: dict[str, str]
    platform_metrics: dict[str, object]
    notes: tuple[str, ...] = ()


class MobileAgentV35MobileSafetyBenchBridgeAdapter(OpenAutoGLMMobileSafetyBenchBridgeAdapter):
    @property
    def adapter_id(self) -> str:
        return "mobile_agent_v3_5__mobilesafetybench"

    @property
    def agent_id(self) -> str:
        return "mobile_agent_v3_5"

    @property
    def benchmark_id(self) -> str:
        return "mobilesafetybench"

    def describe_bridge(self) -> BridgeContract:
        return BridgeContract(
            bridge_id=self.adapter_id,
            agent_id=self.agent_id,
            benchmark_id=self.benchmark_id,
            integration_mode=IntegrationMode.HYBRID,
            observation_mapping_entry=(
                "MobileSafetyEnv.reset/get_state -> ObservationBundle -> "
                "Mobile-Agent-v3.5 wrapped runner"
            ),
            action_mapping_entry=(
                "Mobile-Agent-v3.5 tool_call JSON stays agent-owned while the bridge owns "
                "MobileSafetyBench reset, bootstrap observation capture, and final-state evaluation"
            ),
            run_entry=(
                "MobileAgentV35MobileSafetyBenchBridgeAdapter.run_wrapped_pair"
            ),
            environment_handshake_entry=(
                "existing Android emulator lease + MobileSafetyEnv reset + "
                "Mobile-Agent-v3.5 subprocess runner"
            ),
            artifact_capture_hooks=(
                "trial/raw/mobile_agent_v3_5_mobilesafetybench/bridge_request.json",
                "trial/raw/mobile_agent_v3_5_mobilesafetybench/environment_init.console.txt",
                "trial/raw/mobile_agent_v3_5_mobilesafetybench/bootstrap_observation.json",
                "trial/raw/mobile_agent_v3_5_mobilesafetybench/final_observation.json",
                "trial/raw/mobile_agent_v3_5_mobilesafetybench/final_result.json",
                "trial/raw/mobile_agent_v3_5/runner_result.json",
                "trial/trajectory.json",
            ),
            supported_backends=("adb_appium",),
            required_env=(
                "MOBILE_AGENT_V3_5_HOME",
                "MOBILE_SAFETY_HOME",
                "ANDROID_SDK_ROOT",
                "APPIUM_BIN",
            ),
            requires_pair_recipe=True,
        )

    def map_observation(self, observation: ObservationBundle) -> ObservationBundle:
        extra = dict(observation.extra)
        extra.setdefault("bridge_id", self.adapter_id)
        extra.setdefault("pair_mode", "mobile_agent_v3_5_x_mobilesafetybench")
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
            source_backend=observation.source_backend or "bridge.mobile_agent_v3_5_msb",
            extra=extra,
        )

    def map_action(self, raw_action: object) -> object:
        if not isinstance(raw_action, dict):
            return "no-op()"
        normalized = str(raw_action.get("normalized_action", "")).strip()
        if normalized == "finish":
            finish_flag = str(raw_action.get("finish_flag", "")).strip()
            if finish_flag in {"manual_interaction", "unsafe", "refuse"}:
                return "refuse()"
            return "complete()"
        if normalized == "manual_interaction":
            return "ask-consent()"
        if normalized == "launch_app":
            return "launch()"
        if normalized == "type_text":
            return "replace-text()"
        if normalized == "tap":
            return "tap()"
        if normalized == "swipe":
            return "swipe()"
        if normalized == "wait":
            return "no-op()"
        return "no-op()"

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
    ) -> MobileAgentV35MobileSafetyBenchRunRequest:
        return MobileAgentV35MobileSafetyBenchRunRequest(
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
        request: MobileAgentV35MobileSafetyBenchRunRequest,
    ) -> MobileAgentV35MobileSafetyBenchRunResult:
        if request.mock_mode:
            return self._run_mock_pair(request)
        return self._run_real_pair(request)

    def run_trial(self, ctx: TrialContext) -> object:
        raise IntegrationError(
            "This bridge requires a structured run request. Use build_run_request() + run_wrapped_pair()."
        )

    def _run_mock_pair(
        self,
        request: MobileAgentV35MobileSafetyBenchRunRequest,
    ) -> MobileAgentV35MobileSafetyBenchRunResult:
        benchmark_adapter = MobileSafetyBenchBenchmarkAdapter()
        agent_adapter = MobileAgentV35AgentAdapter()
        ctx = request.trial_context
        benchmark_adapter.prepare_trial(ctx)
        benchmark_adapter.seed_environment(ctx)
        observation = self.map_observation(benchmark_adapter.get_initial_observation(ctx))
        agent_request = agent_adapter.build_run_request(
            ctx,
            output_dir=request.output_dir,
            observation=observation,
            task_instruction=request.task_instruction,
            model_spec=request.model_spec,
            emulator_instance=request.emulator_instance,
            task_payload=request.task_payload,
            mock_mode=True,
        )
        agent_result = agent_adapter.run_wrapped_agent(agent_request)
        task = benchmark_adapter.resolve_task(ctx.trial_spec.task_id)
        score_bundle = benchmark_adapter.build_score_bundle(
            task=task,
            native_metrics=dict(agent_result.native_metrics or {}),
        )

        bridge_raw_dir = request.output_dir / "raw" / "mobile_agent_v3_5_mobilesafetybench"
        bridge_raw_dir.mkdir(parents=True, exist_ok=True)
        request_path = bridge_raw_dir / "bridge_request.json"
        result_path = bridge_raw_dir / "final_result.json"
        request_path.write_text(
            json.dumps(self._request_payload(request), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        result_path.write_text(
            json.dumps(
                {
                    "score_bundle": {
                        "native_metrics": score_bundle.native_metrics,
                        "primary_metric": score_bundle.primary_metric,
                        "platform_metrics": score_bundle.platform_metrics,
                    },
                    "agent_platform_metrics": dict(agent_result.platform_metrics),
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        filtered_agent_notes = tuple(
            note
            for note in agent_result.notes
            if "Benchmark-native scoring remains provisional" not in note
        )
        return MobileAgentV35MobileSafetyBenchRunResult(
            score_bundle=score_bundle,
            trajectory_steps=agent_result.trajectory_steps,
            raw_artifacts={
                "bridge_request_path": str(request_path),
                "final_result_path": str(result_path),
                **agent_result.raw_artifacts,
            },
            platform_metrics={
                **score_bundle.platform_metrics,
                "bridge_mode": "mock",
                "steps_executed": len(agent_result.trajectory_steps),
            },
            notes=tuple(
                dict.fromkeys(
                    [
                        *filtered_agent_notes,
                        "Mock pair bridge path executed. Real MobileSafetyBench environment and Mobile-Agent-v3.5 runtime were not invoked.",
                    ]
                )
            ),
        )

    def _run_real_pair(
        self,
        request: MobileAgentV35MobileSafetyBenchRunRequest,
    ) -> MobileAgentV35MobileSafetyBenchRunResult:
        self._validate_real_env(request)
        mobile_agent_v35_repo = resolve_mobile_agent_v3_5_repo_path()
        mobilesafetybench_repo = resolve_mobilesafetybench_repo_path()
        ctx = request.trial_context
        task = MobileSafetyBenchBenchmarkAdapter().resolve_task(ctx.trial_spec.task_id)
        trial_logger = get_trial_logger(
            ctx.trial_spec.trial_id,
            request.output_dir / "trial.log",
        )
        trial_logger.info(
            "Starting MobileSafetyBench task '%s' (%s)",
            task.task_id,
            task.instruction,
        )
        LOGGER.info(
            "Starting real pair run for trial '%s' on device '%s' with task '%s'",
            ctx.trial_spec.trial_id,
            request.emulator_instance.adb_serial,
            task.task_id,
        )
        LOGGER.info(
            "Trial '%s' execution budget: max_steps=%s",
            ctx.trial_spec.trial_id,
            ctx.trial_spec.max_steps,
        )

        bridge_raw_dir = request.output_dir / "raw" / "mobile_agent_v3_5_mobilesafetybench"
        bridge_raw_dir.mkdir(parents=True, exist_ok=True)
        request_path = bridge_raw_dir / "bridge_request.json"
        result_path = bridge_raw_dir / "final_result.json"
        failure_path = bridge_raw_dir / "failure.json"
        request_path.write_text(
            json.dumps(self._request_payload(request), indent=2, sort_keys=True),
            encoding="utf-8",
        )

        self._prepare_shared_runtime_environment(
            repo_paths=[mobilesafetybench_repo],
            env_vars={
                "MOBILE_AGENT_V3_5_HOME": str(mobile_agent_v35_repo),
                "MOBILE_SAFETY_HOME": str(mobilesafetybench_repo),
            },
        )
        with self._patched_mobilesafetybench_sms_helpers(trial_logger=trial_logger):
            env: object | None = None
            started_at = time.monotonic()
            environment_console_path = bridge_raw_dir / "environment_init.console.txt"
            try:
                preflight_failures = self._probe_benchmark_runtime_imports()
                if preflight_failures:
                    raise IntegrationError(self._format_benchmark_import_failure(preflight_failures))
                try:
                    from mobile_safety.environment import MobileSafetyEnv
                except Exception as error:
                    raise IntegrationError(
                        "failed to import MobileSafetyBench runtime modules. "
                        "Check upstream dependencies and local checkout integrity. "
                        f"Original error: {type(error).__name__}: {error}"
                    ) from error

                adb_port = self._adb_port_from_serial(request.emulator_instance.adb_serial)
                LOGGER.info(
                    "Bootstrapping MobileSafetyBench environment on adb serial '%s' (port=%s)",
                    request.emulator_instance.adb_serial,
                    adb_port,
                )
                self._wait_for_device_bootstrap_ready(
                    adb_serial=request.emulator_instance.adb_serial,
                    trial_logger=trial_logger,
                )
                snapshot_name = request.emulator_instance.snapshot_name or "test_env_100"
                trial_logger.info(
                    "Environment initialization started: restore snapshot '%s' and seed MobileSafetyBench task state",
                    snapshot_name,
                )
                try:
                    env, timestep = self._reset_environment_with_existing_device_recovery(
                        env_builder=lambda: self._build_environment(
                            MobileSafetyEnv=MobileSafetyEnv,
                            task=task,
                            emulator_instance=request.emulator_instance,
                            adb_port=adb_port,
                        ),
                        snapshot_name=snapshot_name,
                        output_dir=request.output_dir,
                        environment_console_path=environment_console_path,
                        trial_logger=trial_logger,
                        adb_serial=request.emulator_instance.adb_serial,
                    )
                except Exception as error:
                    raise IntegrationError(
                        "MobileSafetyBench task invocation failed during environment reset/seed. "
                        "Check snapshot availability, Appium, and adb connectivity. "
                        f"Initialization transcript: {environment_console_path}"
                    ) from error
                bootstrap_observation, bootstrap_xml_content, bootstrap_pixel_array = self._build_real_observation(
                    env=env,
                    timestep=timestep,
                    task=task,
                    benchmark_action="no-op()",
                )
                bootstrap_observation = self._persist_bridge_observation(
                    output_dir=request.output_dir,
                    bridge_raw_dir=bridge_raw_dir,
                    observation=bootstrap_observation,
                    xml_content=bootstrap_xml_content,
                    pixel_array=bootstrap_pixel_array,
                    stem="bootstrap",
                )
                trial_logger.info(
                    "Environment initialization completed. Transcript saved to %s",
                    environment_console_path,
                )

                agent_adapter = MobileAgentV35AgentAdapter()
                benchmark_adapter = MobileSafetyBenchBenchmarkAdapter()
                runtime_env = build_mobile_agent_v3_5_runtime_env(
                    provider=request.model_spec.provider,
                    model_id=request.model_spec.model_id,
                    adb_serial=request.emulator_instance.adb_serial,
                )
                LOGGER.info(
                    "Initialized Mobile-Agent-v3.5 with model '%s' against '%s'",
                    runtime_env.get("MOBILE_AGENT_V3_5_MODEL", request.model_spec.model_id),
                    runtime_env.get("MOBILE_AGENT_V3_5_BASE_URL", ""),
                )
                agent_request = agent_adapter.build_run_request(
                    ctx,
                    output_dir=request.output_dir,
                    observation=bootstrap_observation,
                    task_instruction=request.task_instruction,
                    model_spec=request.model_spec,
                    emulator_instance=request.emulator_instance,
                    task_payload=request.task_payload,
                    mock_mode=False,
                )
                try:
                    agent_result = agent_adapter.run_wrapped_agent(agent_request)
                except Exception as error:
                    raise IntegrationError(
                        "Mobile-Agent-v3.5 runtime invocation failed inside the pair bridge. "
                        f"Original error: {type(error).__name__}: {error}"
                    ) from error
                try:
                    env.prev_act = "no-op()"
                    final_timestep = self._get_state_with_existing_device_recovery(
                        env=env,
                        adb_serial=request.emulator_instance.adb_serial,
                        trial_logger=trial_logger,
                        state_label="Final environment state capture",
                    )
                except Exception as error:
                    raise IntegrationError(
                        "MobileSafetyBench task invocation failed while fetching the final environment state."
                    ) from error
                final_observation, final_xml_content, final_pixel_array = self._build_real_observation(
                    env=env,
                    timestep=final_timestep,
                    task=task,
                    benchmark_action="no-op()",
                )
                final_observation = self._persist_bridge_observation(
                    output_dir=request.output_dir,
                    bridge_raw_dir=bridge_raw_dir,
                    observation=final_observation,
                    xml_content=final_xml_content,
                    pixel_array=final_pixel_array,
                    stem="final",
                )
                native_metrics, evaluation_notes = self._build_bridge_native_metrics(
                    task=task,
                    final_progress=dict(getattr(final_timestep, "progress", {}) or {}),
                    final_xml_content=final_xml_content,
                    agent_result=agent_result,
                )
                LOGGER.info(
                    "Trial '%s' starting evaluation with final benchmark progress snapshot",
                    ctx.trial_spec.trial_id,
                )
                score_bundle = benchmark_adapter.build_score_bundle(
                    task=task,
                    native_metrics=native_metrics,
                )
                total_duration_ms = max(1, int((time.monotonic() - started_at) * 1000))
                filtered_agent_notes = tuple(
                    note
                    for note in agent_result.notes
                    if "Benchmark-native scoring remains provisional" not in note
                )
                bridge_notes = (
                    "Real pair bridge path executed against a running Android emulator.",
                    "MobileSafetyBench owned reset, task seeding, bootstrap observation capture, and final-state evaluation before and after the Mobile-Agent-v3.5 subprocess run.",
                    "Step-level evaluator progress remains partial because Mobile-Agent-v3.5 executes its own ADB loop outside MobileSafetyEnv.step().",
                )
                combined_notes = tuple(
                    dict.fromkeys([*filtered_agent_notes, *bridge_notes, *evaluation_notes])
                )
                platform_metrics = {
                    **score_bundle.platform_metrics,
                    "duration_ms": total_duration_ms,
                    "bridge_mode": "real",
                    "steps_executed": len(agent_result.trajectory_steps),
                    "upstream_task_duration_sec": agent_result.platform_metrics.get(
                        "upstream_task_duration_sec",
                        0.0,
                    ),
                    "agent_finish_flag": agent_result.platform_metrics.get("finish_flag", ""),
                }
                result_path.write_text(
                    json.dumps(
                        {
                            "score_bundle": {
                                "native_metrics": score_bundle.native_metrics,
                                "primary_metric": score_bundle.primary_metric,
                                "platform_metrics": score_bundle.platform_metrics,
                            },
                            "platform_metrics": platform_metrics,
                            "bootstrap_observation": {
                                "screenshot_path": bootstrap_observation.screenshot_path,
                                "xml_path": bootstrap_observation.xml_path,
                                "parsed_text": bootstrap_observation.parsed_text,
                            },
                            "final_observation": {
                                "screenshot_path": final_observation.screenshot_path,
                                "xml_path": final_observation.xml_path,
                                "parsed_text": final_observation.parsed_text,
                            },
                        },
                        indent=2,
                        sort_keys=True,
                    ),
                    encoding="utf-8",
                )
                LOGGER.info(
                    "Trial '%s' evaluation completed: goal_achievement=%s harm_prevention=%s primary_metric=%s",
                    ctx.trial_spec.trial_id,
                    score_bundle.native_metrics.get("goal_achievement"),
                    score_bundle.native_metrics.get("harm_prevention"),
                    score_bundle.primary_metric,
                )
                LOGGER.info(
                    "Trial '%s' evaluation finalized: primary_metric=%s step_count=%s finished=%s",
                    ctx.trial_spec.trial_id,
                    score_bundle.primary_metric,
                    score_bundle.native_metrics.get("step_count"),
                    score_bundle.native_metrics.get("finished"),
                )
                if bool(score_bundle.native_metrics.get("finished", False)):
                    trial_logger.info(
                        "Task finished with primary_metric=%s and native_metrics=%s",
                        score_bundle.primary_metric,
                        json.dumps(score_bundle.native_metrics, ensure_ascii=False, sort_keys=True),
                    )
                else:
                    trial_logger.info(
                        "Task evaluation completed without benchmark-finished state: primary_metric=%s and native_metrics=%s",
                        score_bundle.primary_metric,
                        json.dumps(score_bundle.native_metrics, ensure_ascii=False, sort_keys=True),
                    )
                for note in evaluation_notes:
                    LOGGER.info(
                        "Trial '%s' evaluation reconciliation: %s",
                        ctx.trial_spec.trial_id,
                        note,
                    )
                    trial_logger.info("Evaluation reconciliation: %s", note)
                return MobileAgentV35MobileSafetyBenchRunResult(
                    score_bundle=score_bundle,
                    trajectory_steps=agent_result.trajectory_steps,
                    raw_artifacts={
                        "bridge_request_path": str(request_path),
                        "environment_init_console_path": str(environment_console_path),
                        "bootstrap_observation_path": str(bridge_raw_dir / "bootstrap_observation.json"),
                        "final_observation_path": str(bridge_raw_dir / "final_observation.json"),
                        "final_result_path": str(result_path),
                        **agent_result.raw_artifacts,
                    },
                    platform_metrics=platform_metrics,
                    notes=combined_notes,
                )
            except Exception as error:
                failure_payload = {
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                    "traceback": traceback.format_exc(),
                }
                failure_path.write_text(
                    json.dumps(failure_payload, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
                trial_logger.error(
                    "Mobile-Agent-v3.5 x MobileSafetyBench pair bridge failed: %s",
                    error,
                )
                raise IntegrationError(
                    "Mobile-Agent-v3.5 x MobileSafetyBench pair bridge failed. "
                    f"See {failure_path} for traceback and bridge diagnostics."
                ) from error
            finally:
                if env is not None:
                    self._cleanup_existing_device_environment(env)

    def _wait_for_device_bootstrap_ready(
        self,
        *,
        adb_serial: str,
        trial_logger: logging.Logger,
        timeout_sec: int = 45,
    ) -> None:
        deadline = time.monotonic() + timeout_sec
        last_failure = "device readiness probe not started"
        LOGGER.info(
            "Waiting for device '%s' to become adb-ready before MobileSafetyBench bootstrap",
            adb_serial,
        )
        trial_logger.info(
            "Waiting for device '%s' readiness before benchmark environment bootstrap",
            adb_serial,
        )
        while time.monotonic() < deadline:
            wait_result = self._run_adb_command(
                ("adb", "-s", adb_serial, "wait-for-device"),
                timeout_sec=15,
                allow_failure=True,
            )
            if wait_result.returncode != 0:
                last_failure = self._describe_command_failure(wait_result)
                time.sleep(1.0)
                continue

            state_result = self._run_adb_command(
                ("adb", "-s", adb_serial, "get-state"),
                timeout_sec=15,
                allow_failure=True,
            )
            state = state_result.stdout.strip()
            if state_result.returncode != 0 or state != "device":
                last_failure = (
                    self._describe_command_failure(state_result)
                    if state_result.returncode != 0
                    else f"adb get-state returned '{state or 'unknown'}'"
                )
                time.sleep(1.0)
                continue

            boot_result = self._run_adb_command(
                ("adb", "-s", adb_serial, "shell", "getprop", "sys.boot_completed"),
                timeout_sec=15,
                allow_failure=True,
            )
            boot_completed = boot_result.stdout.strip().splitlines()[-1:] == ["1"]
            if boot_result.returncode != 0 or not boot_completed:
                last_failure = (
                    self._describe_command_failure(boot_result)
                    if boot_result.returncode != 0
                    else f"sys.boot_completed returned '{boot_result.stdout.strip()}'"
                )
                time.sleep(1.0)
                continue

            size_result = self._run_adb_command(
                ("adb", "-s", adb_serial, "shell", "wm", "size"),
                timeout_sec=15,
                allow_failure=True,
            )
            if size_result.returncode != 0 or "Physical size:" not in size_result.stdout:
                last_failure = (
                    self._describe_command_failure(size_result)
                    if size_result.returncode != 0
                    else f"wm size returned unexpected output '{size_result.stdout.strip()}'"
                )
                time.sleep(1.0)
                continue

            LOGGER.info(
                "Device '%s' is ready for MobileSafetyBench bootstrap (%s)",
                adb_serial,
                size_result.stdout.strip(),
            )
            trial_logger.info(
                "Device readiness check passed before benchmark bootstrap (%s)",
                size_result.stdout.strip(),
            )
            return

        raise IntegrationError(
            "Timed out waiting for the leased emulator to become ready for benchmark bootstrap. "
            f"Last probe failure: {last_failure}"
        )

    def _log_agent_execution_trace(
        self,
        *,
        trial_id: str,
        trial_logger: logging.Logger,
        trajectory_steps: tuple[object, ...],
    ) -> None:
        for step in trajectory_steps:
            step_index = getattr(step, "step_index", 0)
            trial_logger.info("Step %s started", step_index)
            LOGGER.info("Trial '%s' step %s started", trial_id, step_index)

            thought = str(getattr(step, "thought", "") or "").strip()
            if thought:
                trial_logger.info("Step %s thought: %s", step_index, thought)

            action_summary = self._render_step_action_for_log(step)
            if action_summary:
                trial_logger.info("Step %s action selected: %s", step_index, action_summary)

            observation = getattr(step, "observation", None)
            package_name = getattr(observation, "package_name", None)
            activity = getattr(observation, "activity", None)
            trial_logger.info(
                "Step %s observation captured: package=%s activity=%s",
                step_index,
                package_name,
                activity,
            )

            action = getattr(step, "action", None)
            executed_action = dict(getattr(action, "executed_action", {}) or {})
            action_status = dict(getattr(action, "execution_result", {}) or {}).get("action_status", {})
            LOGGER.info(
                "Trial '%s' step %s completed: action=%s status=%s",
                trial_id,
                step_index,
                executed_action.get("action_name") or executed_action.get("normalized_action") or "",
                dict(action_status or {}).get("ok", True),
            )

    def _render_step_action_for_log(self, step: object) -> str:
        action = getattr(step, "action", None)
        parsed_action = dict(getattr(action, "parsed_action", {}) or {})
        executed_action = dict(getattr(action, "executed_action", {}) or {})
        arguments = parsed_action.get("arguments")
        if isinstance(arguments, dict):
            action_name = str(arguments.get("action", "")).strip()
            payload = {key: value for key, value in arguments.items() if key != "action"}
            if payload:
                return f"{action_name} {json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
            return action_name
        return str(executed_action.get("action_name") or executed_action.get("normalized_action") or "").strip()

    def _request_payload(
        self,
        request: MobileAgentV35MobileSafetyBenchRunRequest,
    ) -> dict[str, object]:
        return {
            "trial_id": request.trial_context.trial_spec.trial_id,
            "benchmark_id": request.trial_context.trial_spec.benchmark_id,
            "task_id": request.trial_context.trial_spec.task_id,
            "agent_id": request.trial_context.trial_spec.agent_id,
            "model_id": request.model_spec.model_id,
            "adb_serial": request.emulator_instance.adb_serial,
            "avd_name": request.emulator_instance.avd_name,
            "mock_mode": request.mock_mode,
            "runtime_recipe": request.trial_context.trial_spec.runtime_recipe.to_dict(),
            "task_payload": request.task_payload,
        }

    def _validate_real_env(self, request: MobileAgentV35MobileSafetyBenchRunRequest) -> None:
        if not os.environ.get("APPIUM_BIN", "").strip():
            resolved_appium = shutil.which("appium")
            if resolved_appium:
                os.environ["APPIUM_BIN"] = resolved_appium
        missing = []
        if not os.environ.get("APPIUM_BIN"):
            missing.append("APPIUM_BIN (or appium on PATH)")
        if missing:
            raise IntegrationError(
                "real Mobile-Agent-v3.5 x MobileSafetyBench bridge runs require these environment variables: "
                + ", ".join(missing)
            )
        resolve_mobile_agent_v3_5_repo_path()
        resolve_mobilesafetybench_repo_path()
        if request.emulator_instance.adb_serial.strip() == "":
            raise DeviceError(
                "no adb serial is attached to the leased emulator instance; start an emulator and confirm it appears in `adb devices`"
            )
        if "image" not in request.model_spec.modalities or not request.model_spec.supports_image_input:
            raise IntegrationError(
                "Mobile-Agent-v3.5 requires a model with text+image modalities and image input support"
            )
        try:
            build_mobile_agent_v3_5_runtime_env(
                provider=request.model_spec.provider,
                model_id=request.model_spec.model_id,
                adb_serial=request.emulator_instance.adb_serial,
            )
        except IntegrationError as error:
            raise IntegrationError(
                "Mobile-Agent-v3.5 model/runtime config is incomplete for the pair bridge. "
                f"{error}"
            ) from error

    def _probe_benchmark_runtime_imports(self) -> list[tuple[str, str, str, str]]:
        checks = (("MobileSafetyBench", "mobile_safety.environment"),)
        failures: list[tuple[str, str, str, str]] = []
        for owner, module_name in checks:
            try:
                importlib.import_module(module_name)
            except Exception as error:
                failures.append((owner, module_name, type(error).__name__, str(error)))
        return failures

    def _format_benchmark_import_failure(
        self,
        failures: list[tuple[str, str, str, str]],
    ) -> str:
        details = "; ".join(
            f"{owner}:{module_name} -> {error_type}: {message}"
            for owner, module_name, error_type, message in failures
        )
        return (
            "MobileSafetyBench runtime import preflight failed. "
            f"Details: {details}. Install the upstream benchmark requirements into the active Python environment, "
            "for example: `python -m pip install -r references/benchmarks/mobilesafetybench/requirements.txt`."
        )

    def _persist_bridge_observation(
        self,
        *,
        output_dir: Path,
        bridge_raw_dir: Path,
        observation: ObservationBundle,
        xml_content: str,
        pixel_array: object,
        stem: str,
    ) -> ObservationBundle:
        screenshot_path = bridge_raw_dir / f"{stem}.png"
        xml_path = bridge_raw_dir / f"{stem}.xml"
        observation_path = bridge_raw_dir / f"{stem}_observation.json"
        self._write_png_from_observation_extra(screenshot_path, pixel_array)
        xml_path.write_text(
            xml_content if xml_content else "<hierarchy></hierarchy>\n",
            encoding="utf-8",
        )
        relative_screenshot = str(screenshot_path.relative_to(output_dir))
        relative_xml = str(xml_path.relative_to(output_dir))
        persisted = ObservationBundle(
            timestamp=observation.timestamp,
            screenshot_path=relative_screenshot,
            xml_path=relative_xml,
            ui_tree_json_path=observation.ui_tree_json_path,
            parsed_text=observation.parsed_text,
            activity=observation.activity,
            package_name=observation.package_name,
            screen_size=observation.screen_size,
            orientation=observation.orientation,
            source_backend=observation.source_backend,
            extra=dict(observation.extra),
        )
        observation_path.write_text(
            json.dumps(
                {
                    "timestamp": persisted.timestamp,
                    "screenshot_path": persisted.screenshot_path,
                    "xml_path": persisted.xml_path,
                    "parsed_text": persisted.parsed_text,
                    "package_name": persisted.package_name,
                    "screen_size": persisted.screen_size,
                    "source_backend": persisted.source_backend,
                    "extra": dict(persisted.extra),
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return persisted

    def _build_bridge_native_metrics(
        self,
        *,
        task: object,
        final_progress: dict[str, object],
        final_xml_content: str,
        agent_result: object,
    ) -> tuple[dict[str, object], tuple[str, ...]]:
        agent_platform_metrics = dict(getattr(agent_result, "platform_metrics", {}) or {})
        agent_native_metrics = dict(getattr(agent_result, "native_metrics", {}) or {})
        benchmark_finished = bool(final_progress.get("finished", False))
        native_metrics = {
            "goal_achievement": bool(final_progress.get("goal achievement", False)),
            "harm_prevention": bool(final_progress.get("harm prevention", False)),
            "risk_detected_step": int(final_progress.get("risk-detected step", -1)),
            "finished": benchmark_finished,
            "step_count": max(
                int(final_progress.get("step", 0)),
                len(getattr(agent_result, "trajectory_steps", ()) or ()),
            ),
            "risk_level": task.risk_level,
            "task_category": task.task_category,
            "benchmark_task_id": task.task_id,
        }
        native_metrics, reconciliation_notes = self._reconcile_native_metrics_with_ui_evidence(
            task=task,
            native_metrics=native_metrics,
            final_xml_content=final_xml_content,
        )
        notes = list(reconciliation_notes)
        agent_finished = bool(agent_platform_metrics.get("finished", False))
        agent_finish_flag = str(agent_platform_metrics.get("finish_flag", "")).strip()
        if agent_finished and not bool(native_metrics.get("finished", False)):
            finish_detail = f" finish_flag={agent_finish_flag}." if agent_finish_flag else "."
            notes.append(
                "Mobile-Agent-v3.5 reported a stop/terminate signal, but MobileSafetyBench did not "
                "mark the task finished and the final UI snapshot did not provide enough evidence to "
                f"reconcile completion.{finish_detail}"
            )
        if (
            task.risk_level == "high_risk"
            and not bool(native_metrics.get("harm_prevention", False))
            and bool(agent_native_metrics.get("harm_prevention", False))
        ):
            notes.append(
                "Mobile-Agent-v3.5 reported a safe stop, but the bridge kept benchmark-native "
                "harm_prevention=false because MobileSafetyBench progress and final UI evidence did "
                "not confirm task completion."
            )
        return native_metrics, tuple(notes)
