from __future__ import annotations

import importlib
import json
import logging
import os
import shutil
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from snowl_mobile.adapters.agents.mobile_agent_e import (
    MobileAgentEAgentAdapter,
    MobileAgentELiveEvent,
    MobileAgentEStepTranscript,
    resolve_mobile_agent_e_repo_path,
)
from snowl_mobile.adapters.benchmarks.mobilesafetybench import (
    MobileSafetyBenchBenchmarkAdapter,
    MobileSafetyBenchTask,
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


def _utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class MobileAgentEMobileSafetyBenchRunRequest:
    trial_context: TrialContext
    output_dir: Path
    emulator_instance: EmulatorInstance
    model_spec: ModelSpec
    task_payload: dict[str, object]
    task_instruction: str
    mock_mode: bool = False


@dataclass(frozen=True, slots=True)
class MobileAgentEMobileSafetyBenchRunResult:
    score_bundle: ScoreBundle
    trajectory_steps: tuple[object, ...]
    raw_artifacts: dict[str, str]
    platform_metrics: dict[str, object]
    notes: tuple[str, ...] = ()


class MobileAgentEMobileSafetyBenchBridgeAdapter(OpenAutoGLMMobileSafetyBenchBridgeAdapter):
    @property
    def adapter_id(self) -> str:
        return "mobile_agent_e__mobilesafetybench"

    @property
    def agent_id(self) -> str:
        return "mobile_agent_e"

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
                "Mobile-Agent-E wrapped runner"
            ),
            action_mapping_entry=(
                "Mobile-Agent-E JSON actions stay agent-owned while the bridge owns "
                "MobileSafetyBench environment bootstrap and final-state evaluation"
            ),
            run_entry=(
                "MobileAgentEMobileSafetyBenchBridgeAdapter.run_wrapped_pair"
            ),
            environment_handshake_entry=(
                "existing Android emulator lease + MobileSafetyEnv reset + "
                "Mobile-Agent-E subprocess runner"
            ),
            artifact_capture_hooks=(
                "trial/raw/mobile_agent_e_mobilesafetybench/bridge_request.json",
                "trial/raw/mobile_agent_e_mobilesafetybench/environment_init.console.txt",
                "trial/raw/mobile_agent_e_mobilesafetybench/final_result.json",
                "trial/raw/mobile_agent_e_mobilesafetybench/steps/0001.console.txt",
                "trial/raw/mobile_agent_e/runner_result.json",
                "trial/trajectory.json",
            ),
            supported_backends=("adb_appium",),
            required_env=(
                "MOBILE_AGENT_E_HOME",
                "MOBILE_SAFETY_HOME",
                "ANDROID_SDK_ROOT",
                "APPIUM_BIN",
            ),
            requires_pair_recipe=True,
        )

    def map_observation(self, observation: ObservationBundle) -> ObservationBundle:
        extra = dict(observation.extra)
        extra.setdefault("bridge_id", self.adapter_id)
        extra.setdefault("pair_mode", "mobile_agent_e_x_mobilesafetybench")
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
            source_backend=observation.source_backend or "bridge.mobile_agent_e_msb",
            extra=extra,
        )

    def map_action(self, raw_action: object) -> object:
        if not isinstance(raw_action, dict):
            return "no-op()"
        action_name = str(raw_action.get("name", "")).strip()
        if action_name == "Back":
            return "button(BACK)"
        if action_name == "Home":
            return "button(HOME)"
        if action_name == "Enter":
            return "enter()"
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
    ) -> MobileAgentEMobileSafetyBenchRunRequest:
        return MobileAgentEMobileSafetyBenchRunRequest(
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
        request: MobileAgentEMobileSafetyBenchRunRequest,
    ) -> MobileAgentEMobileSafetyBenchRunResult:
        if request.mock_mode:
            return self._run_mock_pair(request)
        return self._run_real_pair(request)

    def run_trial(self, ctx: TrialContext) -> object:
        raise IntegrationError(
            "This bridge requires a structured run request. Use build_run_request() + run_wrapped_pair()."
        )

    def _run_mock_pair(
        self,
        request: MobileAgentEMobileSafetyBenchRunRequest,
    ) -> MobileAgentEMobileSafetyBenchRunResult:
        benchmark_adapter = MobileSafetyBenchBenchmarkAdapter()
        agent_adapter = MobileAgentEAgentAdapter()
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
            native_metrics=dict(agent_result.native_metrics),
        )

        bridge_raw_dir = request.output_dir / "raw" / "mobile_agent_e_mobilesafetybench"
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
        return MobileAgentEMobileSafetyBenchRunResult(
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
            notes=(
                "Mock pair bridge path executed. Real MobileSafetyBench environment and Mobile-Agent-E runtime were not invoked.",
            ),
        )

    def _run_real_pair(
        self,
        request: MobileAgentEMobileSafetyBenchRunRequest,
    ) -> MobileAgentEMobileSafetyBenchRunResult:
        self._validate_real_env(request)
        mobile_agent_e_repo = resolve_mobile_agent_e_repo_path()
        mobilesafetybench_repo = resolve_mobilesafetybench_repo_path()
        repo_paths = [mobilesafetybench_repo]
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
        bridge_raw_dir = request.output_dir / "raw" / "mobile_agent_e_mobilesafetybench"
        bridge_raw_dir.mkdir(parents=True, exist_ok=True)
        request_path = bridge_raw_dir / "bridge_request.json"
        result_path = bridge_raw_dir / "final_result.json"
        failure_path = bridge_raw_dir / "failure.json"
        request_path.write_text(
            json.dumps(self._request_payload(request), indent=2, sort_keys=True),
            encoding="utf-8",
        )

        self._prepare_shared_runtime_environment(
            repo_paths=repo_paths,
            env_vars={
                "MOBILE_AGENT_E_HOME": str(mobile_agent_e_repo),
                "MOBILE_SAFETY_HOME": str(mobilesafetybench_repo),
            },
        )
        with self._patched_mobilesafetybench_sms_helpers(trial_logger=trial_logger):
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
            self._wait_for_device_bootstrap_ready(
                adb_serial=request.emulator_instance.adb_serial,
                trial_logger=trial_logger,
            )
            env = None
            snapshot_name = request.emulator_instance.snapshot_name or "test_env_100"
            environment_console_path = bridge_raw_dir / "environment_init.console.txt"
            started_at = time.monotonic()
            try:
                trial_logger.info(
                    "Environment initialization started: restore snapshot '%s' and seed MobileSafetyBench task state",
                    snapshot_name,
                )
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

                agent_adapter = MobileAgentEAgentAdapter()
                benchmark_adapter = MobileSafetyBenchBenchmarkAdapter()
                streamed_step_indices: set[int] = set()

                def live_event_callback(event: MobileAgentELiveEvent) -> None:
                    if event.event_type == "status":
                        LOGGER.info(
                            "Trial '%s': %s",
                            ctx.trial_spec.trial_id,
                            event.message,
                        )
                        trial_logger.info("%s", event.message)
                        return
                    if event.event_type != "step" or event.step_transcript is None:
                        return
                    transcript = event.step_transcript
                    if transcript.step_index in streamed_step_indices:
                        return
                    streamed_step_indices.add(transcript.step_index)
                    LOGGER.info(
                        "Trial '%s' step %s materialized live from Mobile-Agent-E transcript",
                        ctx.trial_spec.trial_id,
                        transcript.step_index,
                    )
                    self._materialize_single_pair_step_artifact(
                        output_dir=request.output_dir,
                        bridge_raw_dir=bridge_raw_dir,
                        transcript=transcript,
                    )
                    self._log_single_agent_step_trace(
                        trial_logger=trial_logger,
                        transcript=transcript,
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
                    live_event_callback=live_event_callback,
                )
                agent_result = agent_adapter.run_wrapped_agent(agent_request)
                pair_step_artifacts = self._materialize_pair_step_artifacts(
                    output_dir=request.output_dir,
                    bridge_raw_dir=bridge_raw_dir,
                    agent_result=agent_result,
                    skip_step_indices=streamed_step_indices,
                )
                self._log_agent_step_trace(
                    trial_logger=trial_logger,
                    task=task,
                    agent_result=agent_result,
                    skip_step_indices=streamed_step_indices,
                )

                env.prev_act = "no-op()"
                final_timestep = self._get_state_with_existing_device_recovery(
                    env=env,
                    adb_serial=request.emulator_instance.adb_serial,
                    trial_logger=trial_logger,
                    state_label="Final environment state capture",
                )
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
                    "MobileSafetyBench owned reset, task seeding, and final-state evaluation before and after the Mobile-Agent-E subprocess run.",
                    "Step-level MobileSafetyBench action reconciliation remains partial because Mobile-Agent-E executes its own ADB loop outside MobileSafetyEnv.step().",
                )
                combined_notes = tuple(dict.fromkeys([*filtered_agent_notes, *bridge_notes, *evaluation_notes]))
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
                return MobileAgentEMobileSafetyBenchRunResult(
                    score_bundle=score_bundle,
                    trajectory_steps=agent_result.trajectory_steps,
                    raw_artifacts={
                        "bridge_request_path": str(request_path),
                        "final_result_path": str(result_path),
                        "environment_init_console_path": str(environment_console_path),
                        **pair_step_artifacts,
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
                raise IntegrationError(
                    "Mobile-Agent-E x MobileSafetyBench pair bridge failed. "
                    f"See {failure_path} for traceback and bridge diagnostics."
                ) from error
            finally:
                self._cleanup_existing_device_environment(env)

    def _materialize_pair_step_artifacts(
        self,
        *,
        output_dir: Path,
        bridge_raw_dir: Path,
        agent_result: object,
        skip_step_indices: set[int] | None = None,
    ) -> dict[str, str]:
        raw_artifacts = dict(getattr(agent_result, "raw_artifacts", {}))
        steps_json_path_raw = str(raw_artifacts.get("steps_json_path", "")).strip()
        if not steps_json_path_raw:
            return {}
        steps_json_path = Path(steps_json_path_raw)
        if not steps_json_path.exists():
            return {}
        steps_payload = json.loads(steps_json_path.read_text(encoding="utf-8"))
        if not isinstance(steps_payload, list):
            return {}

        planning_entries: dict[int, dict[str, object]] = {}
        action_entries: dict[int, dict[str, object]] = {}
        reflection_entries: dict[int, dict[str, object]] = {}
        for item in steps_payload:
            if not isinstance(item, dict):
                continue
            try:
                step_number = int(item.get("step", 0))
            except (TypeError, ValueError):
                continue
            operation = str(item.get("operation", "")).strip()
            if operation == "planning":
                planning_entries[step_number] = item
            elif operation == "action":
                action_entries[step_number] = item
            elif operation == "action_reflection":
                reflection_entries[step_number] = item

        pair_steps_dir = bridge_raw_dir / "steps"
        pair_steps_dir.mkdir(parents=True, exist_ok=True)
        materialized: dict[str, str] = {}
        skipped = skip_step_indices or set()
        for step in getattr(agent_result, "trajectory_steps", ()):
            step_index = int(getattr(step, "step_index", 0))
            if step_index in skipped:
                continue
            transcript = MobileAgentEStepTranscript(
                step_index=step_index,
                step_number=step_index,
                trajectory_step=step,
                planning_entry=planning_entries.get(step_index),
                action_entry=action_entries.get(step_index),
                reflection_entry=reflection_entries.get(step_index),
            )
            materialized.update(
                self._materialize_single_pair_step_artifact(
                    output_dir=output_dir,
                    bridge_raw_dir=bridge_raw_dir,
                    transcript=transcript,
                )
            )
        return materialized

    def _materialize_single_pair_step_artifact(
        self,
        *,
        output_dir: Path,
        bridge_raw_dir: Path,
        transcript: MobileAgentEStepTranscript,
    ) -> dict[str, str]:
        step_index = transcript.step_index
        pair_steps_dir = bridge_raw_dir / "steps"
        pair_steps_dir.mkdir(parents=True, exist_ok=True)
        console_path = pair_steps_dir / f"{step_index:04d}.console.txt"
        console_text = self._render_step_console(
            step_index=step_index,
            planning_entry=transcript.planning_entry,
            action_entry=transcript.action_entry,
            reflection_entry=transcript.reflection_entry,
        )
        console_path.write_text(console_text, encoding="utf-8")
        materialized = {f"step_{step_index:04d}_console_path": str(console_path)}

        artifacts = getattr(transcript.trajectory_step, "artifacts", None)
        model_text_rel = getattr(artifacts, "model_response_text_path", None)
        model_json_rel = getattr(artifacts, "model_response_json_path", None)
        if model_text_rel:
            source_text = output_dir / str(model_text_rel)
            if source_text.exists():
                destination_text = pair_steps_dir / f"{step_index:04d}.model_response.txt"
                shutil.copy2(source_text, destination_text)
                materialized[f"step_{step_index:04d}_model_response_text_path"] = str(
                    destination_text
                )
        if model_json_rel:
            source_json = output_dir / str(model_json_rel)
            if source_json.exists():
                destination_json = pair_steps_dir / f"{step_index:04d}.model_response.json"
                shutil.copy2(source_json, destination_json)
                materialized[f"step_{step_index:04d}_model_response_json_path"] = str(
                    destination_json
                )
        return materialized

    def _render_step_console(
        self,
        *,
        step_index: int,
        planning_entry: dict[str, object] | None,
        action_entry: dict[str, object] | None,
        reflection_entry: dict[str, object] | None,
    ) -> str:
        sections: list[str] = [f"Step {step_index}"]
        if planning_entry is not None:
            sections.extend(
                [
                    "### Manager ... ###",
                    f"Thought: {str(planning_entry.get('thought', '')).strip()}",
                    f"Overall Plan: {str(planning_entry.get('plan', '')).strip()}",
                    f"Current Subgoal: {str(planning_entry.get('current_subgoal', '')).strip()}",
                ]
            )
        if action_entry is not None:
            action_object = action_entry.get("action_object")
            action_repr = (
                json.dumps(action_object, ensure_ascii=False)
                if isinstance(action_object, dict)
                else str(action_entry.get("action_object_str", "")).strip()
            )
            sections.extend(
                [
                    "### Operator ... ###",
                    f"Action Thought: {str(action_entry.get('action_thought', '')).strip()}",
                    f"Action Description: {str(action_entry.get('action_description', '')).strip()}",
                    f"Action: {action_repr}",
                ]
            )
        if reflection_entry is not None:
            sections.extend(
                [
                    "### Action Reflector ... ###",
                    f"Outcome: {str(reflection_entry.get('outcome', '')).strip()}",
                    f"Progress Status: {str(reflection_entry.get('progress_status', '')).strip()}",
                    f"Error Description: {str(reflection_entry.get('error_description', '')).strip()}",
                ]
            )
        return "\n\n".join(section for section in sections if section.strip()) + "\n"

    def _log_agent_step_trace(
        self,
        *,
        trial_logger: logging.Logger,
        task: MobileSafetyBenchTask,
        agent_result: object,
        skip_step_indices: set[int] | None = None,
    ) -> None:
        raw_artifacts = dict(getattr(agent_result, "raw_artifacts", {}))
        steps_json_path_raw = str(raw_artifacts.get("steps_json_path", "")).strip()
        planning_entries: dict[int, dict[str, object]] = {}
        action_entries: dict[int, dict[str, object]] = {}
        reflection_entries: dict[int, dict[str, object]] = {}
        if steps_json_path_raw:
            steps_json_path = Path(steps_json_path_raw)
            if steps_json_path.exists():
                try:
                    steps_payload = json.loads(steps_json_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    steps_payload = []
                if isinstance(steps_payload, list):
                    for item in steps_payload:
                        if not isinstance(item, dict):
                            continue
                        try:
                            step_number = int(item.get("step", 0))
                        except (TypeError, ValueError):
                            continue
                        operation = str(item.get("operation", "")).strip()
                        if operation == "planning":
                            planning_entries[step_number] = item
                        elif operation == "action":
                            action_entries[step_number] = item
                        elif operation == "action_reflection":
                            reflection_entries[step_number] = item

        skipped = skip_step_indices or set()
        for step in getattr(agent_result, "trajectory_steps", ()):
            step_index = int(getattr(step, "step_index", 0))
            if step_index in skipped:
                continue
            LOGGER.info(
                "Trial '%s' step %s reconstructed from Mobile-Agent-E transcript",
                task.task_id,
                step_index,
            )
            self._log_single_agent_step_trace(
                trial_logger=trial_logger,
                transcript=MobileAgentEStepTranscript(
                    step_index=step_index,
                    step_number=step_index,
                    trajectory_step=step,
                    planning_entry=planning_entries.get(step_index),
                    action_entry=action_entries.get(step_index),
                    reflection_entry=reflection_entries.get(step_index),
                ),
            )

    def _log_single_agent_step_trace(
        self,
        *,
        trial_logger: logging.Logger,
        transcript: MobileAgentEStepTranscript,
    ) -> None:
        step_index = transcript.step_index
        step = transcript.trajectory_step
        action_text = str(getattr(step, "action_text", "")).strip()
        observation = getattr(step, "observation", None)
        notes = list(getattr(step, "notes", []) or [])
        planning_entry = transcript.planning_entry
        action_entry = transcript.action_entry
        reflection_entry = transcript.reflection_entry
        progress_status = ""
        reflection_outcome = ""
        action_description = ""
        for note in notes:
            if isinstance(note, str) and note.startswith("progress_status: "):
                progress_status = note.split(": ", 1)[1]
        if observation is not None:
            reflection_outcome = str(getattr(observation, "extra", {}).get("reflection_outcome", "")).strip()
        if action_entry is not None:
            action_description = str(action_entry.get("action_description", "")).strip()
        if reflection_entry is not None and not progress_status:
            progress_status = str(reflection_entry.get("progress_status", "")).strip()

        trial_logger.info("Step %s started", step_index)
        if planning_entry is not None:
            thought = str(planning_entry.get("thought", "")).strip()
            plan = str(planning_entry.get("plan", "")).strip()
            current_subgoal = str(planning_entry.get("current_subgoal", "")).strip()
            if thought:
                trial_logger.info("Step %s manager thought: %s", step_index, thought)
            if plan:
                trial_logger.info("Step %s plan: %s", step_index, plan)
            if current_subgoal:
                trial_logger.info("Step %s subgoal: %s", step_index, current_subgoal)
        action_thought = str(getattr(step, "thought", "")).strip()
        if action_thought:
            trial_logger.info("Step %s action thought: %s", step_index, action_thought)
        if action_description:
            trial_logger.info("Step %s action description: %s", step_index, action_description)
        if action_text:
            trial_logger.info("Step %s action selected: %s", step_index, action_text)
        if observation is not None:
            trial_logger.info(
                "Step %s observation captured: screenshot=%s xml=%s",
                step_index,
                getattr(observation, "screenshot_path", None),
                getattr(observation, "xml_path", None),
            )
        if progress_status:
            trial_logger.info("Step %s progress: %s", step_index, progress_status)
        if reflection_outcome:
            trial_logger.info("Step %s reflection outcome: %s", step_index, reflection_outcome)
        if reflection_entry is not None:
            error_description = str(reflection_entry.get("error_description", "")).strip()
            if error_description and error_description != "None":
                trial_logger.info("Step %s reflection detail: %s", step_index, error_description)

    def _request_payload(
        self,
        request: MobileAgentEMobileSafetyBenchRunRequest,
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

    def _validate_real_env(self, request: MobileAgentEMobileSafetyBenchRunRequest) -> None:
        if not os.environ.get("APPIUM_BIN", "").strip():
            resolved_appium = shutil.which("appium")
            if resolved_appium:
                os.environ["APPIUM_BIN"] = resolved_appium
        missing = []
        if not os.environ.get("APPIUM_BIN"):
            missing.append("APPIUM_BIN (or appium on PATH)")
        if missing:
            raise IntegrationError(
                "real Mobile-Agent-E x MobileSafetyBench bridge runs require these environment variables: "
                + ", ".join(missing)
            )
        resolve_mobile_agent_e_repo_path()
        resolve_mobilesafetybench_repo_path()
        if request.emulator_instance.adb_serial.strip() == "":
            raise DeviceError("no adb serial is attached to the leased emulator instance")
        if "image" not in request.model_spec.modalities or not request.model_spec.supports_image_input:
            raise IntegrationError(
                "Mobile-Agent-E requires a model with text+image modalities and image input support"
            )

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
        task: MobileSafetyBenchTask,
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
                "Mobile-Agent-E reported a stop/terminate signal, but MobileSafetyBench did not "
                "mark the task finished and the final UI snapshot did not provide enough evidence to "
                f"reconcile completion.{finish_detail}"
            )
        if (
            task.risk_level == "high_risk"
            and not bool(native_metrics.get("harm_prevention", False))
            and bool(agent_native_metrics.get("harm_prevention", False))
        ):
            notes.append(
                "Mobile-Agent-E reported a safe stop, but the bridge kept benchmark-native "
                "harm_prevention=false because MobileSafetyBench progress and final UI evidence did "
                "not confirm task completion."
            )
        return native_metrics, tuple(notes)
