from __future__ import annotations

import json
import os
import random
import shutil
import sys
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Any

from snowl_mobile.adapters.agents.mobile_agent_e import (
    MobileAgentEAgentAdapter,
    MobileAgentELiveEvent,
    MobileAgentERunRequest,
    MobileAgentEStepTranscript,
)
from snowl_mobile.adapters.bridges.open_autoglm_androidworld_runtime import (
    _copy_external_output,
    _ensure_androidworld_accessibility_runtime,
    _format_observation_preview,
    _format_trial_start_message,
    _initialize_androidworld_task_with_contact_fallback,
    _load_json,
    _looks_like_a11y_forwarder_download_failure,
    _patch_androidworld_a11y_forwarder_install,
    _patch_androidworld_clear_directory,
    _patch_androidworld_datetime_utils,
    _patch_androidworld_sms_validator_time,
    _patch_androidworld_sqlite_fts4_support,
    _persist_observation,
    _relative_to_trial,
    _require_runtime_import,
    _resolve_task_instruction,
    _run_androidworld_env_operation,
    _run_androidworld_task_bootstrap_with_recovery,
    _safe_value,
    _score_androidworld_task_with_missing_table_recovery,
    _setup_task_scoped_apps,
    _warn_if_androidworld_device_profile_unsupported,
    _write_json,
)
from snowl_mobile.core.errors import IntegrationError
from snowl_mobile.core.logging import get_trial_logger
from snowl_mobile.schemas.observation import ObservationBundle


def _mobile_agent_e_lightweight_perception_enabled() -> bool:
    return os.environ.get("MOBILE_AGENT_E_LIGHTWEIGHT_PERCEPTION", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _relative_path_under_trial(path_value: str | Path | None, *, trial_dir: Path) -> str | None:
    if not path_value:
        return None
    candidate = Path(path_value)
    if not candidate.is_absolute():
        candidate = (trial_dir / candidate).resolve()
    try:
        return candidate.relative_to(trial_dir).as_posix()
    except Exception:
        return str(path_value)


def _resolve_step_source(path_value: str | Path | None, *, trial_dir: Path) -> Path | None:
    if not path_value:
        return None
    candidate = Path(path_value)
    if not candidate.is_absolute():
        candidate = trial_dir / candidate
    return candidate


def _collect_step_entries(steps_payload: object) -> tuple[
    dict[int, dict[str, object]],
    dict[int, dict[str, object]],
    dict[int, dict[str, object]],
]:
    planning_entries: dict[int, dict[str, object]] = {}
    action_entries: dict[int, dict[str, object]] = {}
    reflection_entries: dict[int, dict[str, object]] = {}
    if not isinstance(steps_payload, list):
        return planning_entries, action_entries, reflection_entries
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
    return planning_entries, action_entries, reflection_entries


def _render_step_console(
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


def _materialize_single_pair_step_artifact(
    *,
    output_dir: Path,
    bridge_raw_dir: Path,
    transcript: MobileAgentEStepTranscript,
) -> dict[str, str]:
    step_index = transcript.step_index
    pair_steps_dir = bridge_raw_dir / "steps"
    pair_steps_dir.mkdir(parents=True, exist_ok=True)
    console_path = pair_steps_dir / f"{step_index:04d}.console.txt"
    console_path.write_text(
        _render_step_console(
            step_index=step_index,
            planning_entry=transcript.planning_entry,
            action_entry=transcript.action_entry,
            reflection_entry=transcript.reflection_entry,
        ),
        encoding="utf-8",
    )
    materialized = {
        f"step_{step_index:04d}_console_path": _relative_to_trial(console_path, trial_dir=output_dir)
    }

    artifacts = getattr(transcript.trajectory_step, "artifacts", None)
    model_text_rel = getattr(artifacts, "model_response_text_path", None)
    model_json_rel = getattr(artifacts, "model_response_json_path", None)
    if model_text_rel:
        source_text = output_dir / str(model_text_rel)
        if source_text.exists():
            destination_text = pair_steps_dir / f"{step_index:04d}.model_response.txt"
            shutil.copy2(source_text, destination_text)
            materialized[f"step_{step_index:04d}_model_response_text_path"] = _relative_to_trial(
                destination_text,
                trial_dir=output_dir,
            )
    if model_json_rel:
        source_json = output_dir / str(model_json_rel)
        if source_json.exists():
            destination_json = pair_steps_dir / f"{step_index:04d}.model_response.json"
            shutil.copy2(source_json, destination_json)
            materialized[f"step_{step_index:04d}_model_response_json_path"] = _relative_to_trial(
                destination_json,
                trial_dir=output_dir,
            )
    return materialized


def _log_single_agent_step_trace(
    *,
    trial_logger: Any,
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
        trial_logger.info(
            "Step %s observation preview: %s",
            step_index,
            _format_observation_preview(asdict(observation)),
        )
    if progress_status:
        trial_logger.info("Step %s progress: %s", step_index, progress_status)
    if reflection_outcome:
        trial_logger.info("Step %s reflection outcome: %s", step_index, reflection_outcome)


def _mirror_platform_step_artifacts(
    *,
    step_payload: dict[str, object],
    trial_dir: Path,
) -> dict[str, str]:
    artifacts = step_payload.get("artifacts", {})
    observation = step_payload.get("observation", {})
    if not isinstance(artifacts, dict) or not isinstance(observation, dict):
        return {}
    step_index = int(step_payload.get("step_index", 0) or 0)
    mirrored: dict[str, str] = {}
    steps_dir = trial_dir / "steps"
    steps_dir.mkdir(parents=True, exist_ok=True)

    source_screenshot = _resolve_step_source(artifacts.get("screenshot_path"), trial_dir=trial_dir)
    if source_screenshot is not None and source_screenshot.exists():
        destination_screenshot = steps_dir / f"{step_index:04d}{source_screenshot.suffix or '.png'}"
        if source_screenshot.resolve() != destination_screenshot.resolve():
            shutil.copy2(source_screenshot, destination_screenshot)
        relative = _relative_to_trial(destination_screenshot, trial_dir=trial_dir)
        observation["screenshot_path"] = relative
        artifacts["screenshot_path"] = relative
        mirrored[f"platform_step_{step_index:04d}_screenshot"] = relative

    source_xml = _resolve_step_source(artifacts.get("xml_path"), trial_dir=trial_dir)
    if source_xml is not None and source_xml.exists():
        destination_xml = steps_dir / f"{step_index:04d}.xml"
        if source_xml.resolve() != destination_xml.resolve():
            shutil.copy2(source_xml, destination_xml)
        relative = _relative_to_trial(destination_xml, trial_dir=trial_dir)
        observation["xml_path"] = relative
        artifacts["xml_path"] = relative
        mirrored[f"platform_step_{step_index:04d}_xml"] = relative

    return mirrored


def _normalize_agent_raw_artifacts(
    *,
    raw_artifacts: dict[str, object],
    trial_dir: Path,
) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in raw_artifacts.items():
        if not isinstance(key, str):
            continue
        normalized[f"mobile_agent_e_{key}"] = str(_relative_path_under_trial(str(value), trial_dir=trial_dir))
    return normalized


def _extract_mobile_agent_e_failure_detail(*, trial_dir: Path) -> dict[str, object]:
    failure_path = trial_dir / "raw" / "mobile_agent_e" / "failure.json"
    if not failure_path.exists():
        return {}
    try:
        payload = json.loads(failure_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _raise_mobile_agent_e_bridge_error(
    *,
    error: IntegrationError,
    trial_dir: Path,
) -> None:
    error_text = str(error)
    if "Missing Mobile-Agent-E runtime env vars" in error_text:
        raise RuntimeError(f"MOBILE_AGENT_E_RUNTIME_ENV_ERROR: {error_text}") from error

    failure_detail = _extract_mobile_agent_e_failure_detail(trial_dir=trial_dir)
    detail_message = str(failure_detail.get("error_message", "") or "").strip()
    detail_traceback = str(failure_detail.get("traceback", "") or "").strip()
    combined_detail = "\n".join(part for part in (detail_message, detail_traceback, error_text) if part)
    lowered_detail = combined_detail.lower()

    if "timed out while calling" in lowered_detail or "returned no response" in lowered_detail:
        raise RuntimeError(f"MODEL_API_ERROR: {detail_message or error_text}") from error
    if any(
        marker in lowered_detail
        for marker in (
            "openai.apiconnectionerror",
            "httpx.connecterror",
            "httpcore.connecterror",
            "ssl: unexpected_eof_while_reading",
            "certificate verify failed",
            "connection timed out",
            "read timeout",
            "connection error",
            "provider returned status",
            "chat.completions",
            "chat/completions",
        )
    ):
        raise RuntimeError(f"MODEL_API_ERROR: {detail_message or error_text}") from error
    if any(
        marker in lowered_detail
        for marker in (
            "device offline",
            "no devices/emulators found",
            "device not found",
            "adb server didn't ack",
            "adb serial",
            "disappeared during execution",
            "emulator was killed",
            "emulator exited",
            "emulator quit",
        )
    ):
        raise RuntimeError(f"ANDROIDWORLD_ENV_ERROR: {detail_message or error_text}") from error
    raise RuntimeError(
        "MOBILE_AGENT_E_BRIDGE_ERROR: "
        f"{detail_message or error_text}"
    ) from error


def _run_pair(request: dict[str, object]) -> dict[str, object]:
    trial_dir = Path(str(request["output_dir"]))
    raw_dir = trial_dir / "raw" / "mobile_agent_e_androidworld"
    raw_dir.mkdir(parents=True, exist_ok=True)
    trial_id = str(request.get("trial_id", "") or "mobile_agent_e__androidworld")
    trial_logger = get_trial_logger(trial_id, trial_dir / "trial.log")

    repo_paths = request.get("repo_paths", {})
    if not isinstance(repo_paths, dict):
        raise RuntimeError("MOBILE_AGENT_E_BRIDGE_ERROR: repo_paths must be a JSON object.")
    mobile_agent_e_repo = Path(str(repo_paths.get("mobile_agent_e", "")))
    androidworld_repo = Path(str(repo_paths.get("androidworld", "")))
    for repo_path in (mobile_agent_e_repo, androidworld_repo):
        if repo_path.as_posix() and repo_path.as_posix() not in sys.path:
            sys.path.insert(0, repo_path.as_posix())

    if not _mobile_agent_e_lightweight_perception_enabled():
        _require_runtime_import(
            "inference_agent_E",
            install_hint="python -m pip install -r references/agents/MobileAgent/Mobile-Agent-E/requirements.txt",
        )
    _require_runtime_import(
        "android_world.env.env_launcher",
        install_hint="python -m pip install -r references/benchmarks/android_world/requirements.txt",
    )

    model_payload = request.get("model", {})
    if not isinstance(model_payload, dict):
        raise RuntimeError("MODEL_CONFIG_ERROR: model payload must be an object.")
    model_id = str(model_payload.get("model_id", "") or "").strip()
    model_provider = str(model_payload.get("provider", "") or "").strip()
    if not model_id:
        raise RuntimeError("MODEL_CONFIG_ERROR: model_id is empty.")
    if not model_provider:
        raise RuntimeError("MODEL_CONFIG_ERROR: provider is empty.")

    benchmark_options = request.get("benchmark_options", {})
    if not isinstance(benchmark_options, dict):
        raise RuntimeError("ANDROIDWORLD_ENV_ERROR: benchmark_options must be an object.")
    task_payload = request.get("task_payload", {})
    if not isinstance(task_payload, dict):
        raise RuntimeError("ANDROIDWORLD_TASK_ERROR: task_payload must be an object.")
    device_payload = request.get("device", {})
    if not isinstance(device_payload, dict):
        raise RuntimeError("ANDROIDWORLD_ENV_ERROR: device payload must be an object.")

    from android_world import registry as androidworld_registry
    from android_world.env import env_launcher

    console_port = int(device_payload.get("console_port") or benchmark_options.get("console_port", 5554))
    grpc_port = int(device_payload.get("grpc_port") or benchmark_options.get("grpc_port", 8554))
    adb_path = str(benchmark_options.get("adb_path", "") or "adb").strip() or "adb"
    perform_emulator_setup = bool(benchmark_options.get("perform_emulator_setup", False))
    freeze_datetime = bool(benchmark_options.get("freeze_datetime", True))
    adb_serial = str(device_payload.get("adb_serial", "") or "").strip()
    if not adb_serial:
        raise RuntimeError("ANDROIDWORLD_ENV_ERROR: adb_serial is empty.")
    if grpc_port < 1:
        raise RuntimeError("ANDROIDWORLD_ENV_ERROR: grpc_port is missing or invalid.")

    restore_clear_directory_patch = _patch_androidworld_clear_directory(trial_logger=trial_logger)
    restore_a11y_patch = _patch_androidworld_a11y_forwarder_install(
        adb_path=adb_path,
        adb_serial=adb_serial,
        trial_logger=trial_logger,
    )
    restore_datetime_patch = _patch_androidworld_datetime_utils(trial_logger=trial_logger)
    restore_sms_time_patch = _patch_androidworld_sms_validator_time(trial_logger=trial_logger)
    restore_sqlite_patch = _patch_androidworld_sqlite_fts4_support(trial_logger=trial_logger)

    trial_logger.info(
        "Environment initialization started: adb_serial=%s console_port=%s grpc_port=%s perform_emulator_setup=%s",
        adb_serial,
        console_port,
        grpc_port,
        perform_emulator_setup,
    )
    device_profile = _warn_if_androidworld_device_profile_unsupported(
        adb_path=adb_path,
        adb_serial=adb_serial,
        trial_logger=trial_logger,
    )
    try:
        env = env_launcher.load_and_setup_env(
            console_port=console_port,
            emulator_setup=perform_emulator_setup,
            freeze_datetime=freeze_datetime,
            adb_path=adb_path,
            grpc_port=grpc_port,
        )
    except Exception as error:
        if _looks_like_a11y_forwarder_download_failure(str(error)):
            raise RuntimeError(
                "ANDROIDWORLD_ENV_ERROR: failed to install or refresh the AndroidWorld accessibility forwarder APK. "
                "If this emulator was prepared before, keep the installed package and retry; otherwise allow HTTPS "
                "access to storage.googleapis.com or run `snowl-mobile benchmark-setup ...` once from a network-ready "
                f"environment. Original error: {error}"
            ) from error
        raise RuntimeError(
            "ANDROIDWORLD_ENV_ERROR: failed to load and setup the AndroidWorld environment. "
            "Launch the emulator from the command line with a gRPC port, for example "
            "`emulator -avd AndroidWorldAvd -no-snapshot -grpc 8554`. "
            f"Original error: {error}"
        ) from error
    _ensure_androidworld_accessibility_runtime(
        adb_path=adb_path,
        adb_serial=adb_serial,
        trial_logger=trial_logger,
        env=env,
        force_reconfigure=True,
    )
    env_ref: dict[str, object] = {"env": env}

    def _reload_env() -> object:
        current_env = env_ref.get("env")
        if current_env is not None:
            try:
                current_env.close()
            except Exception:
                pass
        reloaded_env = env_launcher.load_and_setup_env(
            console_port=console_port,
            emulator_setup=perform_emulator_setup,
            freeze_datetime=freeze_datetime,
            adb_path=adb_path,
            grpc_port=grpc_port,
        )
        _ensure_androidworld_accessibility_runtime(
            adb_path=adb_path,
            adb_serial=adb_serial,
            trial_logger=trial_logger,
            env=reloaded_env,
            force_reconfigure=True,
        )
        env_ref["env"] = reloaded_env
        return reloaded_env

    task_name = str(task_payload.get("task_name", "") or "").strip()
    suite_family = str(task_payload.get("suite_family", benchmark_options.get("suite_family", "android")) or "").strip()
    if not task_name:
        raise RuntimeError("ANDROIDWORLD_TASK_ERROR: task_name is empty.")
    if not suite_family:
        raise RuntimeError("ANDROIDWORLD_TASK_ERROR: suite_family is empty.")

    task_registry = androidworld_registry.TaskRegistry()
    try:
        task_type = task_registry.get_registry(suite_family)[task_name]
    except Exception as error:
        raise RuntimeError(
            f"ANDROIDWORLD_TASK_ERROR: failed to resolve task '{task_name}' in suite '{suite_family}': {error}"
        ) from error

    task_instance_seed = int(task_payload.get("task_instance_seed", benchmark_options.get("task_random_seed", 30)))
    task_instruction = str(request.get("task_instruction") or task_payload.get("instruction") or "").strip()
    task = None
    raw_artifacts: dict[str, str] = {}
    trajectory_steps: list[dict[str, object]] = []
    notes: list[str] = []
    native_metrics = {
        "task_success": 0.0,
        "episode_length": 0,
        "env_reward": 0.0,
    }
    platform_metrics: dict[str, object] = {
        "suite_family": suite_family,
        "task_name": task_name,
        "adb_serial": adb_serial,
        "console_port": console_port,
        "grpc_port": grpc_port,
        "device_sdk_int": device_profile.get("sdk_int", ""),
        "device_android_release": device_profile.get("android_release", ""),
        "device_avd_name": device_profile.get("avd_name", ""),
        "device_product_model": device_profile.get("product_model", ""),
        "perform_emulator_setup": perform_emulator_setup,
        "model_id": model_id,
        "model_provider": model_provider,
        "control_backend": "adb",
        "pair_bridge": "mobile_agent_e__androidworld",
        "python_executable": sys.executable,
        "worker_env_name": str(benchmark_options.get("worker_env_name", "") or ""),
    }

    task_metadata_path = raw_dir / "task.json"
    streamed_step_indices: set[int] = set()
    env_closed = False

    try:
        random.seed(task_instance_seed)
        params = task_type.generate_random_params()
        if not isinstance(params, dict):
            raise RuntimeError(f"AndroidWorld task '{task_name}' returned non-dict params.")
        params.setdefault("seed", task_instance_seed)
        task = task_type(params)
        task_instruction = _resolve_task_instruction(
            task=task,
            fallback_instruction=task_instruction,
            task_name=task_name,
        )
        trial_logger.info(
            _format_trial_start_message(
                suite_family=suite_family,
                task_name=task_name,
                task_instruction=task_instruction,
            )
        )
        trial_logger.info("instruction: %s", task_instruction or "<empty instruction>")
        if not perform_emulator_setup:
            installed_apps = _setup_task_scoped_apps(
                task_type=task,
                env=env,
                install_hint="python -m pip install -r references/benchmarks/android_world/requirements.txt",
                adb_path=adb_path,
                adb_serial=adb_serial,
                trial_logger=trial_logger,
            )
            platform_metrics["setup_apps"] = list(installed_apps)
            trial_logger.info(
                "Task-scoped AndroidWorld app setup completed: %s",
                ", ".join(installed_apps) if installed_apps else "<none>",
            )
            notes.append(
                "AndroidWorld task-scoped app setup completed inside the Mobile-Agent-E pair bridge runtime."
            )
            _ensure_androidworld_accessibility_runtime(
                adb_path=adb_path,
                adb_serial=adb_serial,
                trial_logger=trial_logger,
                env=env_ref["env"],
                force_reconfigure=True,
            )
        def _bootstrap_task_state() -> object:
            current_env = env_ref["env"]
            try:
                if hasattr(task, "initialized"):
                    setattr(task, "initialized", False)
            except Exception:
                pass
            current_env.reset(go_home=bool(getattr(task, "start_on_home_screen", True)))
            _initialize_androidworld_task_with_contact_fallback(
                task=task,
                env=current_env,
                trial_logger=trial_logger,
            )
            return current_env.get_state(wait_to_stabilize=True)

        def _refresh_bootstrap_state() -> None:
            current_env = env_ref["env"]
            if not perform_emulator_setup:
                installed_apps = _setup_task_scoped_apps(
                    task_type=task,
                    env=current_env,
                    install_hint="python -m pip install -r references/benchmarks/android_world/requirements.txt",
                    adb_path=adb_path,
                    adb_serial=adb_serial,
                    trial_logger=trial_logger,
                )
                platform_metrics["setup_apps"] = list(installed_apps)
            _ensure_androidworld_accessibility_runtime(
                adb_path=adb_path,
                adb_serial=adb_serial,
                trial_logger=trial_logger,
                env=current_env,
                force_reconfigure=True,
            )

        _write_json(
            task_metadata_path,
            {
                "task_name": task_name,
                "suite_family": suite_family,
                "goal": str(getattr(task, "goal", "") or ""),
                "instruction": task_instruction,
                "complexity": float(getattr(task, "complexity", 0.0) or 0.0),
                "params": _safe_value(getattr(task, "params", params)),
                "seed": task_instance_seed,
            },
        )
        raw_artifacts["androidworld_task"] = _relative_to_trial(task_metadata_path, trial_dir=trial_dir)

        initial_state = _run_androidworld_task_bootstrap_with_recovery(
            env_ref=env_ref,
            trial_logger=trial_logger,
            task_name=task_name,
            bootstrap_operation=_bootstrap_task_state,
            refresh_bootstrap_state=_refresh_bootstrap_state,
            reload_env=_reload_env,
        )
        env = env_ref["env"]
        initial_observation_payload, initial_artifacts = _persist_observation(
            state=initial_state,
            env=env,
            raw_dir=raw_dir / "bootstrap",
            trial_dir=trial_dir,
        )
        raw_artifacts.update({f"androidworld_{key}": value for key, value in initial_artifacts.items()})
        bootstrap_observation = ObservationBundle(
            timestamp=initial_observation_payload.get("timestamp"),
            screenshot_path=str(initial_observation_payload.get("screenshot_path") or ""),
            xml_path=initial_observation_payload.get("xml_path"),
            ui_tree_json_path=initial_observation_payload.get("ui_tree_json_path"),
            parsed_text=initial_observation_payload.get("parsed_text"),
            activity=initial_observation_payload.get("activity"),
            package_name=initial_observation_payload.get("package_name"),
            screen_size=initial_observation_payload.get("screen_size"),
            orientation=initial_observation_payload.get("orientation"),
            source_backend=str(initial_observation_payload.get("source_backend") or "androidworld"),
            extra=dict(initial_observation_payload.get("extra", {})),
        )
        platform_metrics["goal"] = str(getattr(task, "goal", "") or "")
        platform_metrics["task_complexity"] = float(getattr(task, "complexity", 0.0) or 0.0)
        platform_metrics["task_instance_seed"] = task_instance_seed
        platform_metrics["bootstrap_observation_path"] = bootstrap_observation.screenshot_path
        trial_logger.info(
            "Environment initialization completed. Bootstrap observation saved to %s",
            bootstrap_observation.screenshot_path,
        )
        notes.append("AndroidWorld task bootstrap completed inside the pair-specific Mobile-Agent-E bridge runtime.")

        planning_entries: dict[int, dict[str, object]] = {}
        action_entries: dict[int, dict[str, object]] = {}
        reflection_entries: dict[int, dict[str, object]] = {}
        bridge_raw_dir = trial_dir / "raw" / "mobile_agent_e_androidworld"
        bridge_raw_dir.mkdir(parents=True, exist_ok=True)

        def live_event_callback(event: MobileAgentELiveEvent) -> None:
            if event.event_type == "status":
                if event.message:
                    trial_logger.info("%s", event.message)
                return
            if event.event_type != "step" or event.step_transcript is None:
                return
            transcript = event.step_transcript
            if transcript.step_index in streamed_step_indices:
                return
            streamed_step_indices.add(transcript.step_index)
            raw_artifacts.update(
                _materialize_single_pair_step_artifact(
                    output_dir=trial_dir,
                    bridge_raw_dir=bridge_raw_dir,
                    transcript=transcript,
                )
            )
            _log_single_agent_step_trace(
                trial_logger=trial_logger,
                transcript=transcript,
            )

        agent_request = MobileAgentERunRequest(
            repo_path=mobile_agent_e_repo,
            output_dir=trial_dir,
            model_id=model_id,
            model_provider=model_provider,
            task_instruction=task_instruction,
            observation=bootstrap_observation,
            control_backend="adb",
            max_steps=int(request.get("max_steps", 20) or 20),
            timeout_sec=int(request.get("timeout_sec", 2400) or 2400),
            adb_serial=adb_serial,
            task_payload=task_payload,
            mock_mode=False,
            live_event_callback=live_event_callback,
        )
        agent_adapter = MobileAgentEAgentAdapter()
        try:
            agent_result = agent_adapter.run_wrapped_agent(agent_request)
        except IntegrationError as error:
            _raise_mobile_agent_e_bridge_error(
                error=error,
                trial_dir=trial_dir,
            )

        steps_json_path_raw = str(agent_result.raw_artifacts.get("steps_json_path", "")).strip()
        if steps_json_path_raw:
            steps_json_path = Path(steps_json_path_raw)
            if steps_json_path.exists():
                try:
                    steps_payload = json.loads(steps_json_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    steps_payload = []
                planning_entries, action_entries, reflection_entries = _collect_step_entries(steps_payload)

        for step in agent_result.trajectory_steps:
            step_index = int(getattr(step, "step_index", 0))
            if step_index in streamed_step_indices:
                continue
            transcript = MobileAgentEStepTranscript(
                step_index=step_index,
                step_number=step_index,
                trajectory_step=step,
                planning_entry=planning_entries.get(step_index),
                action_entry=action_entries.get(step_index),
                reflection_entry=reflection_entries.get(step_index),
            )
            raw_artifacts.update(
                _materialize_single_pair_step_artifact(
                    output_dir=trial_dir,
                    bridge_raw_dir=bridge_raw_dir,
                    transcript=transcript,
                )
            )
            _log_single_agent_step_trace(
                trial_logger=trial_logger,
                transcript=transcript,
            )

        raw_artifacts.update(
            _normalize_agent_raw_artifacts(
                raw_artifacts=dict(agent_result.raw_artifacts),
                trial_dir=trial_dir,
            )
        )

        for step in agent_result.trajectory_steps:
            step_payload = _safe_value(step.to_dict())
            if not isinstance(step_payload, dict):
                continue
            raw_artifacts.update(
                _mirror_platform_step_artifacts(
                    step_payload=step_payload,
                    trial_dir=trial_dir,
                )
            )
            trajectory_steps.append(step_payload)

        final_state = _run_androidworld_env_operation(
            env_ref=env_ref,
            trial_logger=trial_logger,
            description=f"final observation capture for '{task_name}'",
            operation=lambda: env_ref["env"].get_state(wait_to_stabilize=True),
            reload_env=_reload_env,
        )
        env = env_ref["env"]
        final_observation, final_artifacts = _persist_observation(
            state=final_state,
            env=env,
            raw_dir=raw_dir / "final",
            trial_dir=trial_dir,
        )
        raw_artifacts.update({f"androidworld_{key}": value for key, value in final_artifacts.items()})
        platform_metrics["final_observation_path"] = str(final_observation.get("screenshot_path") or "")
        platform_metrics["steps_executed"] = len(trajectory_steps)
        platform_metrics["finished"] = bool(agent_result.platform_metrics.get("finished", False))
        platform_metrics["agent_finish_flag"] = str(agent_result.platform_metrics.get("finish_flag", "") or "")
        platform_metrics["upstream_task_duration_sec"] = float(
            agent_result.platform_metrics.get("upstream_task_duration_sec", 0.0) or 0.0
        )
        platform_metrics["successful_actions"] = int(agent_result.platform_metrics.get("successful_actions", 0) or 0)
        platform_metrics["failed_actions"] = int(agent_result.platform_metrics.get("failed_actions", 0) or 0)
        platform_metrics["operation_counts"] = dict(agent_result.platform_metrics.get("operation_counts", {}))
        try:
            native_metrics["task_success"] = _score_androidworld_task_with_missing_table_recovery(
                task=task,
                task_name=task_name,
                env_ref=env_ref,
                trial_logger=trial_logger,
                reload_env=_reload_env,
                notes=notes,
            )
        except Exception as error:
            raise RuntimeError(
                f"ANDROIDWORLD_TASK_ERROR: task scoring failed after execution: {error}"
            ) from error
        native_metrics["episode_length"] = len(trajectory_steps)
        trial_logger.info(
            "Task finished with primary_metric=%s and native_metrics=%s",
            native_metrics["task_success"],
            json.dumps(native_metrics, ensure_ascii=False, sort_keys=True),
        )
        filtered_notes = [
            note
            for note in agent_result.notes
            if "Benchmark-native scoring remains provisional" not in note
        ]
        notes.extend(filtered_notes)
        notes.append("AndroidWorld native scoring completed after the Mobile-Agent-E wrapped step loop.")
        notes.append(
            "Step-level AndroidWorld action reconciliation remains partial because Mobile-Agent-E executes its own ADB loop outside AsyncEnv.execute_action()."
        )
    except RuntimeError:
        raise
    except Exception as error:
        raise RuntimeError(
            f"MOBILE_AGENT_E_BRIDGE_ERROR: unexpected bridge runtime failure: {error}"
        ) from error
    finally:
        current_env = env_ref.get("env", env)
        if current_env is not None and task is not None and bool(getattr(task, "initialized", False)):
            try:
                task.tear_down(current_env)
            except Exception:
                notes.append("AndroidWorld task tear_down raised; continuing after capturing artifacts.")
        try:
            if current_env is not None:
                current_env.close()
                env_closed = True
        except Exception:
            env_closed = False
        restore_sqlite_patch()
        restore_sms_time_patch()
        restore_datetime_patch()
        restore_a11y_patch()
        restore_clear_directory_patch()
    if not env_closed:
        notes.append("AndroidWorld env.close() raised during shutdown; see stderr for details.")

    _copy_external_output(
        source_value=benchmark_options.get("checkpoint_dir"),
        destination_name="checkpoint_dir",
        raw_dir=raw_dir,
        trial_dir=trial_dir,
        raw_artifacts=raw_artifacts,
    )
    _copy_external_output(
        source_value=benchmark_options.get("output_path"),
        destination_name="output_path",
        raw_dir=raw_dir,
        trial_dir=trial_dir,
        raw_artifacts=raw_artifacts,
    )

    return {
        "native_metrics": native_metrics,
        "primary_metric": native_metrics["task_success"],
        "platform_metrics": platform_metrics,
        "raw_artifacts": raw_artifacts,
        "trajectory_steps": trajectory_steps,
        "notes": notes,
    }


def main(argv: list[str]) -> int:
    # Suppress gRPC verbose logging that pollutes adb shell output
    os.environ.setdefault("GRPC_VERBOSITY", "ERROR")
    os.environ.setdefault("GRPC_TRACE", "")

    if len(argv) != 3:
        print(
            "usage: python -m snowl_mobile.adapters.bridges.mobile_agent_e_androidworld_runtime "
            "<request-json> <result-json>",
            file=sys.stderr,
        )
        return 2

    request_path = Path(argv[1]).resolve()
    result_path = Path(argv[2]).resolve()
    request = _load_json(request_path)
    output_dir = Path(str(request.get("output_dir", result_path.parent)))
    raw_dir = output_dir / "raw" / "mobile_agent_e_androidworld"
    raw_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = _run_pair(request)
    except Exception as error:
        failure_path = raw_dir / "failure.json"
        _write_json(
            failure_path,
            {
                "error_type": type(error).__name__,
                "error_message": str(error),
                "traceback": traceback.format_exc(),
            },
        )
        print(traceback.format_exc(), file=sys.stderr)
        return 1

    _write_json(result_path, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
