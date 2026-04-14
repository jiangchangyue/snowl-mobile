from __future__ import annotations

import importlib
import json
import random
import shutil
import sys
import time
import traceback
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from snowl_mobile.adapters.bridges.open_autoglm_androidworld_runtime import (
    _patch_androidworld_sqlite_fts4_support,
    _write_png,
)

_INFORMATION_RETRIEVAL_PROTO_RELATIVE_PATHS = (
    "android_world/task_evals/information_retrieval/proto/state.proto",
    "android_world/task_evals/information_retrieval/proto/task.proto",
)


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected a JSON object in '{path.as_posix()}'.")
    return payload


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _safe_value(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, dict):
        return {str(key): _safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_value(item) for item in value]
    if is_dataclass(value):
        return _safe_value(asdict(value))
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return item()
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        return {
            key: _safe_value(item)
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return repr(value)


def _orientation_name(value: object) -> str:
    mapping = {
        0: "portrait",
        1: "landscape",
        2: "reverse_portrait",
        3: "reverse_landscape",
    }
    return mapping.get(value, "unknown")


def _serialize_ui_elements(ui_elements: list[object]) -> list[dict[str, object]]:
    attribute_names = (
        "text",
        "content_description",
        "hint_text",
        "resource_id",
        "class_name",
        "package_name",
        "bounds",
        "is_clickable",
        "is_editable",
        "is_enabled",
        "is_focused",
        "is_focusable",
        "is_long_clickable",
        "is_scrollable",
        "is_selected",
    )
    serialized: list[dict[str, object]] = []
    for element in ui_elements:
        item: dict[str, object] = {}
        for name in attribute_names:
            if not hasattr(element, name):
                continue
            try:
                value = getattr(element, name)
            except Exception:
                continue
            if value in (None, "", [], ()):
                continue
            item[name] = _safe_value(value)
        if not item:
            item["repr"] = repr(element)
        serialized.append(item)
    return serialized


def _extract_text(ui_elements: list[dict[str, object]]) -> str:
    chunks: list[str] = []
    for element in ui_elements:
        for key in ("text", "content_description", "hint_text", "resource_id"):
            value = element.get(key)
            if isinstance(value, str) and value.strip():
                chunks.append(value.strip())
    return "\n".join(list(dict.fromkeys(chunks))[:50])


def _relative_to_trial(path: Path, *, trial_dir: Path) -> str:
    return path.relative_to(trial_dir).as_posix()


def _extract_missing_package_name(message: str) -> str:
    marker = "No module named "
    if marker not in message:
        return ""
    raw = message.split(marker, 1)[1].strip().strip("'\"")
    return raw.split(".", 1)[0]


def _build_install_hint(benchmark_options: dict[str, object]) -> str:
    requirements_file = benchmark_options.get("requirements_file", "")
    if isinstance(requirements_file, str) and requirements_file.strip():
        return f"python -m pip install -r {requirements_file.strip()}"
    return "python -m pip install -r references/benchmarks/android_world/requirements.txt"


def _require_runtime_import(module_name: str, *, install_hint: str) -> None:
    try:
        importlib.import_module(module_name)
    except Exception as error:
        missing = _extract_missing_package_name(str(error))
        package_hint = (
            f" Missing package appears to be '{missing}'."
            if missing
            else ""
        )
        raise RuntimeError(
            "RUNTIME_IMPORT_ERROR: failed to import "
            f"'{module_name}' from the configured AndroidWorld worker interpreter."
            f"{package_hint} Install the upstream dependencies, for example `{install_hint}`."
        ) from error


def _ensure_androidworld_proto_bindings(repo_path: Path, *, install_hint: str) -> None:
    proto_dir = repo_path / "android_world" / "task_evals" / "information_retrieval" / "proto"
    expected_outputs = (
        proto_dir / "state_pb2.py",
        proto_dir / "task_pb2.py",
    )
    if all(path.exists() for path in expected_outputs):
        return

    try:
        import pkg_resources
        from grpc_tools import protoc
    except Exception as error:
        raise RuntimeError(
            "PROTO_GENERATION_ERROR: AndroidWorld proto bindings are missing and "
            "grpc_tools is unavailable in the configured worker interpreter. "
            f"Install the upstream dependencies, for example `{install_hint}`."
        ) from error

    grpc_protos_include = Path(pkg_resources.resource_filename("grpc_tools", "_proto"))
    for relative_path in _INFORMATION_RETRIEVAL_PROTO_RELATIVE_PATHS:
        proto_path = repo_path / relative_path
        proto_args = [
            "grpc_tools.protoc",
            f"--proto_path={grpc_protos_include.as_posix()}",
            f"--proto_path={repo_path.as_posix()}",
            f"--python_out={repo_path.as_posix()}",
            f"--grpc_python_out={repo_path.as_posix()}",
            proto_path.as_posix(),
        ]
        if protoc.main(proto_args) != 0:
            raise RuntimeError(
                "PROTO_GENERATION_ERROR: failed to generate AndroidWorld proto bindings "
                f"for '{relative_path}'."
            )

    missing_outputs = [path.name for path in expected_outputs if not path.exists()]
    if missing_outputs:
        raise RuntimeError(
            "PROTO_GENERATION_ERROR: AndroidWorld proto generation completed without "
            f"creating {', '.join(missing_outputs)}."
        )


def _task_name_from_payload(task_payload: dict[str, object], task_id: str) -> str:
    task_name = task_payload.get("task_name")
    if isinstance(task_name, str) and task_name.strip():
        return task_name.strip()
    parts = [part for part in task_id.split(":") if part]
    if len(parts) < 2:
        raise RuntimeError(f"unable to infer AndroidWorld task name from '{task_id}'.")
    return parts[1]


def _suite_family_from_payload(task_payload: dict[str, object], benchmark_options: dict[str, object]) -> str:
    suite_family = task_payload.get("suite_family", benchmark_options.get("suite_family", "android"))
    if not isinstance(suite_family, str) or not suite_family.strip():
        raise RuntimeError("AndroidWorld suite_family must be a non-empty string.")
    return suite_family.strip()


def _copy_external_output(
    *,
    source_value: object,
    destination_name: str,
    raw_dir: Path,
    trial_dir: Path,
    raw_artifacts: dict[str, str],
) -> None:
    if not isinstance(source_value, str) or not source_value.strip():
        return
    source = Path(source_value).expanduser()
    if not source.exists():
        return
    destination = raw_dir / destination_name
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    raw_artifacts[f"androidworld_{destination_name}"] = _relative_to_trial(destination, trial_dir=trial_dir)


def _persist_observation(
    *,
    state: object,
    env: object,
    raw_dir: Path,
    trial_dir: Path,
) -> tuple[dict[str, object], dict[str, str]]:
    screenshot_path = raw_dir / "observation.png"
    ui_tree_path = raw_dir / "ui_tree.json"
    state_summary_path = raw_dir / "state_summary.json"
    raw_artifacts: dict[str, str] = {}

    _write_png(screenshot_path, getattr(state, "pixels"))
    raw_artifacts["androidworld_screenshot"] = _relative_to_trial(screenshot_path, trial_dir=trial_dir)

    ui_elements = _serialize_ui_elements(list(getattr(state, "ui_elements", [])))
    _write_json(
        ui_tree_path,
        {
            "ui_element_count": len(ui_elements),
            "elements": ui_elements,
        },
    )
    raw_artifacts["androidworld_ui_tree"] = _relative_to_trial(ui_tree_path, trial_dir=trial_dir)

    foreground_activity_name = str(getattr(env, "foreground_activity_name", "") or "")
    logical_screen_size = getattr(env, "logical_screen_size", None)
    if isinstance(logical_screen_size, tuple) and len(logical_screen_size) == 2:
        screen_size = f"{logical_screen_size[0]}x{logical_screen_size[1]}"
    else:
        screen_size = ""
    state_summary = {
        "foreground_activity_name": foreground_activity_name,
        "package_name": foreground_activity_name.split("/")[0] if "/" in foreground_activity_name else "",
        "orientation": _orientation_name(getattr(env, "orientation", None)),
        "screen_size": screen_size,
        "ui_element_count": len(ui_elements),
        "interaction_cache": str(getattr(env, "interaction_cache", "") or ""),
        "auxiliaries": _safe_value(getattr(state, "auxiliaries", None)),
    }
    _write_json(state_summary_path, state_summary)
    raw_artifacts["androidworld_state_summary"] = _relative_to_trial(state_summary_path, trial_dir=trial_dir)

    parsed_text = _extract_text(ui_elements)
    observation = {
        "timestamp": None,
        "screenshot_path": _relative_to_trial(screenshot_path, trial_dir=trial_dir),
        "xml_path": None,
        "ui_tree_json_path": _relative_to_trial(ui_tree_path, trial_dir=trial_dir),
        "parsed_text": parsed_text or None,
        "activity": foreground_activity_name or None,
        "package_name": state_summary["package_name"] or None,
        "screen_size": screen_size or None,
        "orientation": state_summary["orientation"],
        "source_backend": "androidworld",
        "extra": {
            "ui_element_count": len(ui_elements),
            "interaction_cache": state_summary["interaction_cache"],
        },
    }
    return observation, raw_artifacts


def _setup_task_scoped_apps(
    *,
    task_target: object,
    env: object,
    install_hint: str,
) -> tuple[str, ...]:
    from android_world.env import adb_utils
    from android_world.env.setup_device import setup as device_setup

    raw_app_names = getattr(task_target, "app_names", ()) or ()
    app_names = tuple(
        app_name.strip()
        for app_name in raw_app_names
        if isinstance(app_name, str) and app_name.strip()
    )

    adb_utils.press_home_button(env.controller)
    adb_utils.set_root_if_needed(env.controller)

    installed_apps: list[str] = []
    seen: set[str] = set()
    for app_name in app_names:
        if app_name in seen:
            continue
        seen.add(app_name)
        app_class = device_setup.get_app_mapping(app_name)
        if app_class is None:
            continue
        device_setup.maybe_install_app(app_class, env)
        setup_attempts = 0
        while True:
            setup_attempts += 1
            try:
                device_setup.setup_app(app_class, env)
                break
            except Exception as error:
                if not _looks_like_androidworld_a11y_tree_failure(error) or setup_attempts >= 3:
                    if _looks_like_androidworld_a11y_tree_failure(error):
                        raise RuntimeError(
                            "ANDROIDWORLD_ENV_ERROR: AndroidWorld accessibility tree became unavailable during "
                            f"task-scoped app setup for '{app_name}'. The emulator runtime may be unhealthy; "
                            "restart the AVD if this keeps happening. "
                            f"Original error: {error}"
                        ) from error
                    raise
                _recover_androidworld_env_for_setup(env)
        installed_apps.append(app_name)
    return tuple(installed_apps)


def _looks_like_androidworld_a11y_tree_failure(error: Exception | str) -> bool:
    lowered = str(error).lower()
    return "could not get a11y tree" in lowered or "accessibility tree" in lowered


def _recover_androidworld_env_for_setup(env: object) -> None:
    from android_world.env import adb_utils

    controller = getattr(env, "controller", None)
    if controller is None:
        return
    refresh = getattr(controller, "refresh_env", None)
    if callable(refresh):
        refresh()
    adb_utils.press_home_button(controller)
    adb_utils.set_root_if_needed(controller)
    time.sleep(1.0)


def _run_probe(request: dict[str, object]) -> dict[str, object]:
    benchmark_options = request.get("benchmark_options", {})
    if not isinstance(benchmark_options, dict):
        raise RuntimeError("benchmark_options must be a JSON object.")
    task_payload = request.get("task_payload", {})
    if not isinstance(task_payload, dict):
        raise RuntimeError("task_payload must be a JSON object.")

    output_dir = Path(str(request["output_dir"]))
    raw_dir = output_dir / "raw" / "androidworld"
    trial_dir = output_dir
    raw_dir.mkdir(parents=True, exist_ok=True)

    repo_path = Path(str(request["repo_path"]))
    if str(repo_path) not in sys.path:
        sys.path.insert(0, str(repo_path))

    install_hint = _build_install_hint(benchmark_options)
    _ensure_androidworld_proto_bindings(repo_path, install_hint=install_hint)
    console_port = int(request.get("console_port") or benchmark_options.get("console_port", 5554))
    grpc_port = int(request.get("grpc_port") or benchmark_options.get("grpc_port", 8554))
    adb_path = str(benchmark_options.get("adb_path", "") or "adb").strip() or "adb"
    freeze_datetime = bool(benchmark_options.get("freeze_datetime", True))
    operation = str(request.get("operation", "")).strip()
    requested_setup = bool(
        benchmark_options.get("perform_emulator_setup", False)
        or operation == "setup"
    )
    use_upstream_full_setup = bool(
        benchmark_options.get("perform_emulator_setup", False)
        and operation != "setup"
    )

    _require_runtime_import("android_world.env.env_launcher", install_hint=install_hint)
    from android_world.env import env_launcher

    restore_sqlite_patch = _patch_androidworld_sqlite_fts4_support()
    env = env_launcher.load_and_setup_env(
        console_port=console_port,
        emulator_setup=use_upstream_full_setup,
        freeze_datetime=freeze_datetime,
        adb_path=adb_path,
        grpc_port=grpc_port,
    )

    task_name = _task_name_from_payload(task_payload, str(request.get("task_id", "")))
    suite_family = _suite_family_from_payload(task_payload, benchmark_options)

    task = None
    observation: dict[str, object] = {}
    raw_artifacts: dict[str, str] = {}
    native_metrics = {
        "task_success": 0.0,
        "episode_length": 0,
        "env_reward": 0.0,
    }
    platform_metrics: dict[str, object] = {
        "suite_family": suite_family,
        "task_name": task_name,
        "benchmark_operation": str(request.get("operation", "")),
        "console_port": console_port,
        "grpc_port": grpc_port,
        "perform_emulator_setup": requested_setup,
        "upstream_full_setup": use_upstream_full_setup,
    }
    notes: list[str] = []

    try:
        if operation == "setup":
            _require_runtime_import("android_world.registry", install_hint=install_hint)
            from android_world import registry as androidworld_registry

            task_registry = androidworld_registry.TaskRegistry()
            task_type = task_registry.get_registry(suite_family)[task_name]
            task_instance_seed = int(
                task_payload.get("task_instance_seed", benchmark_options.get("task_random_seed", 30))
            )
            random.seed(task_instance_seed)
            params = task_type.generate_random_params()
            if not isinstance(params, dict):
                raise RuntimeError(f"AndroidWorld task '{task_name}' returned non-dict params.")
            params.setdefault("seed", task_instance_seed)
            task = task_type(params)
            installed_apps = _setup_task_scoped_apps(
                task_target=task,
                env=env,
                install_hint=install_hint,
            )
            state = env.reset(go_home=True)
            observation, observation_artifacts = _persist_observation(
                state=state,
                env=env,
                raw_dir=raw_dir,
                trial_dir=trial_dir,
            )
            raw_artifacts.update(observation_artifacts)
            platform_metrics["setup_apps"] = list(installed_apps)
            notes.append(
                "AndroidWorld task-scoped app setup/bootstrap completed through the platform benchmark pipeline."
            )
        else:
            _require_runtime_import("android_world.registry", install_hint=install_hint)
            from android_world import registry as androidworld_registry

            task_registry = androidworld_registry.TaskRegistry()
            task_type = task_registry.get_registry(suite_family)[task_name]
            task_instance_seed = int(task_payload.get("task_instance_seed", benchmark_options.get("task_random_seed", 30)))
            random.seed(task_instance_seed)
            params = task_type.generate_random_params()
            if not isinstance(params, dict):
                raise RuntimeError(f"AndroidWorld task '{task_name}' returned non-dict params.")
            params.setdefault("seed", task_instance_seed)
            task = task_type(params)
            env.reset(go_home=bool(getattr(task, "start_on_home_screen", True)))
            task.initialize_task(env)
            state = env.get_state(wait_to_stabilize=True)
            observation, observation_artifacts = _persist_observation(
                state=state,
                env=env,
                raw_dir=raw_dir,
                trial_dir=trial_dir,
            )
            raw_artifacts.update(observation_artifacts)
            task_success = float(task.is_successful(env))
            native_metrics["task_success"] = task_success
            task_metadata_path = raw_dir / "task.json"
            _write_json(
                task_metadata_path,
                {
                    "task_name": task_name,
                    "suite_family": suite_family,
                    "goal": str(getattr(task, "goal", "") or ""),
                    "instruction": str(request.get("task_instruction", "") or ""),
                    "complexity": float(getattr(task, "complexity", 0.0) or 0.0),
                    "params": _safe_value(getattr(task, "params", params)),
                    "seed": task_instance_seed,
                },
            )
            raw_artifacts["androidworld_task"] = _relative_to_trial(task_metadata_path, trial_dir=trial_dir)
            platform_metrics["goal"] = str(getattr(task, "goal", "") or "")
            platform_metrics["task_complexity"] = float(getattr(task, "complexity", 0.0) or 0.0)
            platform_metrics["task_instance_seed"] = task_instance_seed
            notes.append("AndroidWorld task bootstrap, observation capture, and native scoring completed without an external agent.")
    finally:
        if task is not None and bool(getattr(task, "initialized", False)):
            try:
                task.tear_down(env)
            except Exception:
                notes.append("AndroidWorld task tear_down raised; continuing after capturing artifacts.")
        env.close()
        restore_sqlite_patch()

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
        "observation": observation,
        "native_metrics": native_metrics,
        "primary_metric": native_metrics["task_success"],
        "platform_metrics": platform_metrics,
        "raw_artifacts": raw_artifacts,
        "notes": notes,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(
            "usage: python -m snowl_mobile.adapters.benchmarks.androidworld_runtime "
            "<request-json> <result-json>",
            file=sys.stderr,
        )
        return 2

    request_path = Path(argv[1]).resolve()
    result_path = Path(argv[2]).resolve()
    request = _load_json(request_path)
    output_dir = Path(str(request.get("output_dir", result_path.parent)))
    raw_dir = output_dir / "raw" / "androidworld"
    raw_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = _run_probe(request)
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
