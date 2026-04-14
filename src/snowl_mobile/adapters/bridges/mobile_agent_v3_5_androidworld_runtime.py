from __future__ import annotations

import json
import os
import random
import shutil
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from snowl_mobile.adapters.agents.mobile_agent_v3_5 import (
    MobileAgentV35AgentAdapter,
    MobileAgentV35RunRequest,
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


def _normalize_agent_raw_artifacts(
    *,
    raw_artifacts: dict[str, object],
    trial_dir: Path,
) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in raw_artifacts.items():
        if not isinstance(key, str):
            continue
        normalized[f"mobile_agent_v3_5_{key}"] = str(
            _relative_path_under_trial(str(value), trial_dir=trial_dir)
        )
    return normalized


def _render_step_console(*, step_index: int, step_payload: dict[str, object]) -> str:
    thought = str(step_payload.get("thought", "") or "").strip()
    action_text = str(step_payload.get("action_text", "") or "").strip()
    action_input = step_payload.get("action_input", {})
    observation = step_payload.get("observation", {})
    observation_preview = ""
    if isinstance(observation, dict):
        observation_preview = _format_observation_preview(observation)
    sections: list[str] = [f"Step {step_index}"]
    if thought:
        sections.append(f"Thought: {thought}")
    if action_text:
        sections.append(f"Action: {action_text}")
    if action_input:
        sections.append(
            "Action Input: " + json.dumps(_safe_value(action_input), ensure_ascii=False, sort_keys=True)
        )
    if observation_preview:
        sections.append(f"Observation Preview: {observation_preview}")
    notes = step_payload.get("notes", [])
    if isinstance(notes, list) and notes:
        sections.append(
            "Notes: " + "; ".join(str(note).strip() for note in notes if str(note).strip())
        )
    return "\n\n".join(section for section in sections if section.strip()) + "\n"


def _materialize_single_pair_step_artifact(
    *,
    output_dir: Path,
    bridge_raw_dir: Path,
    step_payload: dict[str, object],
) -> dict[str, str]:
    step_index = int(step_payload.get("step_index", 0) or 0)
    pair_steps_dir = bridge_raw_dir / "steps"
    pair_steps_dir.mkdir(parents=True, exist_ok=True)
    console_path = pair_steps_dir / f"{step_index:04d}.console.txt"
    console_path.write_text(
        _render_step_console(step_index=step_index, step_payload=step_payload),
        encoding="utf-8",
    )
    materialized = {
        f"step_{step_index:04d}_console_path": _relative_to_trial(console_path, trial_dir=output_dir)
    }

    artifacts = step_payload.get("artifacts", {})
    if not isinstance(artifacts, dict):
        return materialized
    model_text_rel = artifacts.get("model_response_text_path")
    model_json_rel = artifacts.get("model_response_json_path")
    if model_text_rel:
        source_text = output_dir / str(model_text_rel)
        if source_text.exists():
            destination_text = pair_steps_dir / f"{step_index:04d}.model_response.txt"
            if source_text.resolve() != destination_text.resolve():
                shutil.copy2(source_text, destination_text)
            materialized[f"step_{step_index:04d}_model_response_text_path"] = _relative_to_trial(
                destination_text,
                trial_dir=output_dir,
            )
    if model_json_rel:
        source_json = output_dir / str(model_json_rel)
        if source_json.exists():
            destination_json = pair_steps_dir / f"{step_index:04d}.model_response.json"
            if source_json.resolve() != destination_json.resolve():
                shutil.copy2(source_json, destination_json)
            materialized[f"step_{step_index:04d}_model_response_json_path"] = _relative_to_trial(
                destination_json,
                trial_dir=output_dir,
            )
    return materialized


def _log_trajectory_step(*, trial_logger: Any, step_payload: dict[str, object]) -> None:
    step_index = int(step_payload.get("step_index", 0) or 0)
    thought = str(step_payload.get("thought", "") or "").strip()
    action_text = str(step_payload.get("action_text", "") or "").strip()
    observation = step_payload.get("observation", {})
    trial_logger.info("Step %s started", step_index)
    if thought:
        trial_logger.info("Step %s action thought: %s", step_index, thought)
    if action_text:
        trial_logger.info("Step %s action selected: %s", step_index, action_text)
    if isinstance(observation, dict):
        trial_logger.info(
            "Step %s observation captured: screenshot=%s xml=%s",
            step_index,
            observation.get("screenshot_path"),
            observation.get("xml_path"),
        )
        trial_logger.info(
            "Step %s observation preview: %s",
            step_index,
            _format_observation_preview(observation),
        )
    notes = step_payload.get("notes", [])
    if isinstance(notes, list):
        for note in notes:
            note_text = str(note).strip()
            if note_text:
                trial_logger.info("Step %s note: %s", step_index, note_text)


def _extract_mobile_agent_v35_failure_detail(*, trial_dir: Path) -> dict[str, object]:
    failure_path = trial_dir / "raw" / "mobile_agent_v3_5" / "failure.json"
    if not failure_path.exists():
        return {}
    try:
        payload = json.loads(failure_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _raise_mobile_agent_v35_bridge_error(
    *,
    error: IntegrationError,
    trial_dir: Path,
) -> None:
    error_text = str(error)
    lowered_error = error_text.lower()
    if "missing mobile-agent-v3.5 runtime env vars" in lowered_error:
        raise RuntimeError(f"MOBILE_AGENT_V3_5_RUNTIME_ENV_ERROR: {error_text}") from error

    failure_detail = _extract_mobile_agent_v35_failure_detail(trial_dir=trial_dir)
    detail_message = str(failure_detail.get("error_message", "") or "").strip()
    detail_traceback = str(failure_detail.get("traceback", "") or "").strip()
    combined_detail = "\n".join(
        part for part in (detail_message, detail_traceback, error_text) if part
    )
    lowered_detail = combined_detail.lower()

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
    if "no such module: fts4" in lowered_detail:
        raise RuntimeError(
            "ANDROIDWORLD_SQLITE_ERROR: "
            f"{detail_message or error_text}"
        ) from error
    if "unsupported mobile-agent-v3.5 action response" in lowered_detail or "invalid json" in lowered_detail:
        raise RuntimeError(f"MOBILE_AGENT_V3_5_BRIDGE_ERROR: {detail_message or error_text}") from error
    raise RuntimeError(
        "MOBILE_AGENT_V3_5_BRIDGE_ERROR: "
        f"{detail_message or error_text}"
    ) from error


def _run_pair(request: dict[str, object]) -> dict[str, object]:
    trial_dir = Path(str(request["output_dir"]))
    raw_dir = trial_dir / "raw" / "mobile_agent_v3_5_androidworld"
    raw_dir.mkdir(parents=True, exist_ok=True)
    trial_id = str(request.get("trial_id", "") or "mobile_agent_v3_5__androidworld")
    trial_logger = get_trial_logger(trial_id, trial_dir / "trial.log")

    repo_paths = request.get("repo_paths", {})
    if not isinstance(repo_paths, dict):
        raise RuntimeError("MOBILE_AGENT_V3_5_BRIDGE_ERROR: repo_paths must be a JSON object.")
    mobile_agent_v35_repo = Path(str(repo_paths.get("mobile_agent_v3_5", "")))
    androidworld_repo = Path(str(repo_paths.get("androidworld", "")))
    for repo_path in (mobile_agent_v35_repo, androidworld_repo):
        if repo_path.as_posix() and repo_path.as_posix() not in sys.path:
            sys.path.insert(0, repo_path.as_posix())

    _require_runtime_import(
        "snowl_mobile.adapters.agents.mobile_agent_v3_5_runner",
        install_hint="python -m pip install openai pillow numpy",
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
    restore_sqlite_patch = _patch_androidworld_sqlite_fts4_support(trial_logger=trial_logger)

    trial_logger.info(
        "Environment initialization started: adb_serial=%s console_port=%s grpc_port=%s perform_emulator_setup=%s",
        adb_serial,
        console_port,
        grpc_port,
        perform_emulator_setup,
    )
    environment_started_at = time.monotonic()
    device_profile = _warn_if_androidworld_device_profile_unsupported(
        adb_path=adb_path,
        adb_serial=adb_serial,
        trial_logger=trial_logger,
    )
    env_load_started_at = time.monotonic()
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
    env_load_duration_ms = max(1, int((time.monotonic() - env_load_started_at) * 1000))
    trial_logger.info(
        "AndroidWorld env load/setup completed in %sms on %s.",
        env_load_duration_ms,
        adb_serial,
    )
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
    suite_family = str(
        task_payload.get("suite_family", benchmark_options.get("suite_family", "android")) or ""
    ).strip()
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
        "pair_bridge": "mobile_agent_v3_5__androidworld",
        "python_executable": sys.executable,
        "worker_env_name": str(benchmark_options.get("worker_env_name", "") or ""),
        "androidworld_env_load_duration_ms": env_load_duration_ms,
    }

    task_metadata_path = raw_dir / "task.json"
    env_closed = False
    env: object | None = env_ref.get("env")

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
                env=env_ref["env"],
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
                "AndroidWorld task-scoped app setup completed inside the Mobile-Agent-v3.5 pair bridge runtime."
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
        platform_metrics["androidworld_environment_duration_ms"] = max(
            1,
            int((time.monotonic() - environment_started_at) * 1000),
        )
        trial_logger.info(
            "Environment initialization completed. Bootstrap observation saved to %s",
            bootstrap_observation.screenshot_path,
        )
        notes.append(
            "AndroidWorld task bootstrap completed inside the pair-specific Mobile-Agent-v3.5 bridge runtime."
        )

        agent_request = MobileAgentV35RunRequest(
            repo_path=mobile_agent_v35_repo,
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
        )
        agent_adapter = MobileAgentV35AgentAdapter()
        try:
            agent_result = agent_adapter.run_wrapped_agent(agent_request)
        except IntegrationError as error:
            _raise_mobile_agent_v35_bridge_error(
                error=error,
                trial_dir=trial_dir,
            )

        raw_artifacts.update(
            _normalize_agent_raw_artifacts(
                raw_artifacts=dict(agent_result.raw_artifacts),
                trial_dir=trial_dir,
            )
        )

        bridge_raw_dir = trial_dir / "raw" / "mobile_agent_v3_5_androidworld"
        bridge_raw_dir.mkdir(parents=True, exist_ok=True)
        for step in agent_result.trajectory_steps:
            step_payload = _safe_value(step.to_dict())
            if not isinstance(step_payload, dict):
                continue
            raw_artifacts.update(
                _materialize_single_pair_step_artifact(
                    output_dir=trial_dir,
                    bridge_raw_dir=bridge_raw_dir,
                    step_payload=step_payload,
                )
            )
            _log_trajectory_step(trial_logger=trial_logger, step_payload=step_payload)
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
        platform_metrics["successful_actions"] = int(
            agent_result.platform_metrics.get("successful_actions", 0) or 0
        )
        platform_metrics["failed_actions"] = int(
            agent_result.platform_metrics.get("failed_actions", 0) or 0
        )
        platform_metrics["operation_counts"] = dict(
            agent_result.platform_metrics.get("operation_counts", {})
        )
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
        notes.append("AndroidWorld native scoring completed after the Mobile-Agent-v3.5 wrapped step loop.")
        notes.append(
            "Step-level AndroidWorld action reconciliation remains partial because Mobile-Agent-v3.5 executes its own ADB loop outside AsyncEnv.execute_action()."
        )
    except RuntimeError:
        raise
    except Exception as error:
        raise RuntimeError(
            f"MOBILE_AGENT_V3_5_BRIDGE_ERROR: unexpected bridge runtime failure: {error}"
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
    os.environ.setdefault("GRPC_VERBOSITY", "ERROR")
    os.environ.setdefault("GRPC_TRACE", "")

    if len(argv) != 3:
        print(
            "usage: python -m snowl_mobile.adapters.bridges.mobile_agent_v3_5_androidworld_runtime "
            "<request-json> <result-json>",
            file=sys.stderr,
        )
        return 2

    request_path = Path(argv[1]).resolve()
    result_path = Path(argv[2]).resolve()
    request = _load_json(request_path)
    output_dir = Path(str(request.get("output_dir", result_path.parent)))
    raw_dir = output_dir / "raw" / "mobile_agent_v3_5_androidworld"
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
