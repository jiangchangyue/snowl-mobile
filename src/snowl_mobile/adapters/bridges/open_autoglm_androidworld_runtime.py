from __future__ import annotations

import contextlib
import dataclasses
import datetime
import importlib
import io
import json
import os
import random
import re
import subprocess
import shutil
import sys
import time
import traceback
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Callable, TypeVar
import xml.etree.ElementTree as ET

from snowl_mobile.core.errors import IntegrationError
from snowl_mobile.core.logging import get_trial_logger
from snowl_mobile.schemas.action import ActionRecord


_T = TypeVar("_T")

_ANDROIDWORLD_A11Y_FORWARDER_PACKAGE = "com.google.androidenv.accessibilityforwarder"
_ANDROIDWORLD_A11Y_FORWARDER_SERVICE = (
    "com.google.androidenv.accessibilityforwarder/"
    "com.google.androidenv.accessibilityforwarder.AccessibilityForwarder"
)
_ANDROIDWORLD_SHELL_DATE_FORMAT = "%a %b %d %H:%M:%S %Z %Y"
_ANDROIDWORLD_SHELL_DATE_PATTERN = re.compile(
    r"[A-Z][a-z]{2}\s+[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+[A-Z]{3,4}\s+\d{4}"
)
_ANDROIDWORLD_UNIX_TIMESTAMP_PATTERN = re.compile(r"(?<!\d)\d{10}(?!\d)")


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
    return "\n".join(list(dict.fromkeys(chunks))[:80])


def _write_ppm(path: Path, pixels: object) -> None:
    height = int(getattr(pixels, "shape", [0, 0])[0])
    width = int(getattr(pixels, "shape", [0, 0])[1])
    if height < 1 or width < 1:
        raise RuntimeError("ANDROIDWORLD_ENV_ERROR: AndroidWorld state.pixels is empty.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(f"P6\n{width} {height}\n255\n".encode("ascii"))
        handle.write(getattr(pixels, "tobytes")())


def _write_png(path: Path, pixels: object) -> None:
    height = int(getattr(pixels, "shape", [0, 0])[0])
    width = int(getattr(pixels, "shape", [0, 0])[1])
    if height < 1 or width < 1:
        raise RuntimeError("ANDROIDWORLD_ENV_ERROR: AndroidWorld state.pixels is empty.")
    try:
        from PIL import Image
    except Exception as error:
        raise RuntimeError("ANDROIDWORLD_ENV_ERROR: Pillow is required to persist AndroidWorld screenshots.") from error
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        Image.fromarray(pixels).save(path)
    except Exception as error:
        raise RuntimeError(f"ANDROIDWORLD_ENV_ERROR: failed to persist screenshot '{path.as_posix()}'.") from error


def _relative_to_trial(path: Path, *, trial_dir: Path) -> str:
    return path.relative_to(trial_dir).as_posix()


def _compact_log_text(text: str | None, *, max_chars: int = 200) -> str:
    if not text:
        return ""
    compact = " ".join(str(text).split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."


def _format_trial_start_message(
    *,
    suite_family: str,
    task_name: str,
    task_instruction: str,
) -> str:
    instruction = _compact_log_text(task_instruction, max_chars=240)
    if instruction:
        return f"Starting AndroidWorld task '{task_name}' ({instruction})"
    return f"Starting AndroidWorld task '{task_name}' from suite '{suite_family}'"


def _format_observation_preview(observation: dict[str, object]) -> str:
    preview = _compact_log_text(str(observation.get("parsed_text") or ""), max_chars=180)
    return preview or "<no visible text>"


class _LiveConsoleTee:
    def __init__(self, terminal_stream: Any, file_paths: list[Path]) -> None:
        self._terminal_stream = terminal_stream
        self._file_handles = []
        for path in file_paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._file_handles.append(path.open("a", encoding="utf-8", buffering=1))
        self._buffer = io.StringIO()

    @property
    def encoding(self) -> str:
        return getattr(self._terminal_stream, "encoding", "utf-8")

    def write(self, data: str) -> int:
        if not data:
            return 0
        self._buffer.write(data)
        with contextlib.suppress(Exception):
            self._terminal_stream.write(data)
            self._terminal_stream.flush()
        for handle in self._file_handles:
            handle.write(data)
            handle.flush()
        return len(data)

    def flush(self) -> None:
        with contextlib.suppress(Exception):
            self._terminal_stream.flush()
        for handle in self._file_handles:
            handle.flush()

    def getvalue(self) -> str:
        return self._buffer.getvalue()

    def close(self) -> None:
        for handle in self._file_handles:
            with contextlib.suppress(Exception):
                handle.flush()
                handle.close()


def _run_with_console_capture(
    operation: Callable[[], _T],
    *,
    file_paths: list[Path],
) -> tuple[_T, str]:
    tee_stream = _LiveConsoleTee(sys.stdout, file_paths)
    try:
        with contextlib.redirect_stdout(tee_stream), contextlib.redirect_stderr(tee_stream):
            result = operation()
    finally:
        tee_stream.flush()
        tee_stream.close()
    return result, tee_stream.getvalue()


def _extract_missing_package_name(message: str) -> str:
    marker = "No module named "
    if marker not in message:
        return ""
    raw = message.split(marker, 1)[1].strip().strip("'\"")
    return raw.split(".", 1)[0]


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
            f"'{module_name}' from the configured AndroidWorld/Open-AutoGLM worker interpreter."
            f"{package_hint} Install the upstream dependencies, for example `{install_hint}`."
        ) from error


def _python_sqlite_supports_fts4() -> bool:
    import sqlite3

    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE VIRTUAL TABLE temp._snowl_fts4_probe USING fts4(content)")
        return True
    except Exception:
        return False
    finally:
        with contextlib.suppress(Exception):
            connection.close()


def _sqlite_cli_fallback_required(error: Exception | str) -> bool:
    lowered = str(error).lower()
    return "no such module: fts4" in lowered or "no such module: fts3" in lowered


def _sqlite_missing_table_error(error: Exception | str) -> bool:
    return "no such table:" in str(error).lower()


def _sqlite_missing_db_path_error(error: Exception | str) -> bool:
    lowered = str(error).lower()
    return "does not exist" in lowered and ("/data/data/" in lowered or ".db" in lowered or "app_db" in lowered)


def _find_sqlite3_cli() -> str:
    return shutil.which("sqlite3") or ""


def _sqlite_literal(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"X'{bytes(value).hex()}'"
    text = str(value).replace("'", "''")
    return f"'{text}'"


def _sqlite_insert_statement(*, row: object, table_name: str, exclude_key: str | None) -> str:
    if dataclasses.is_dataclass(row):
        field_names = [
            field.name
            for field in dataclasses.fields(row)
            if exclude_key is None or field.name != exclude_key
        ]
        values = [getattr(row, field_name) for field_name in field_names]
    else:
        mapping = dict(vars(row))
        if exclude_key is not None:
            mapping.pop(exclude_key, None)
        field_names = list(mapping.keys())
        values = [mapping[field_name] for field_name in field_names]
    columns = ", ".join(f'"{field_name}"' for field_name in field_names)
    sql_values = ", ".join(_sqlite_literal(value) for value in values)
    return f"INSERT INTO {table_name} ({columns}) VALUES ({sql_values});"


def _run_sqlite3_cli(
    *,
    sqlite3_path: str,
    db_path: str | Path,
    sql: str,
    json_output: bool = False,
) -> str:
    command = [sqlite3_path]
    if json_output:
        command.append("-json")
    command.extend([str(db_path), sql])
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "unknown sqlite3 CLI error"
        raise RuntimeError(message)
    return completed.stdout


def _initialize_androidworld_sqlite_owner_app(
    *,
    app_name: str,
    env: object,
    trial_logger: object | None = None,
) -> str:
    _require_runtime_import(
        "android_world.env.setup_device.setup",
        install_hint="python -m pip install -r references/benchmarks/android_world/requirements.txt",
    )
    from android_world.env import adb_utils
    from android_world.env.setup_device import setup as device_setup

    controller = getattr(env, "controller", None)
    if controller is None:
        raise RuntimeError("AndroidWorld environment controller is unavailable while recovering app-owned SQLite data.")

    with contextlib.suppress(Exception):
        adb_utils.press_home_button(controller)
    with contextlib.suppress(Exception):
        adb_utils.set_root_if_needed(controller)

    app_class = device_setup.get_app_mapping(app_name)
    if app_class is not None:
        setup_attempts = 0
        while True:
            setup_attempts += 1
            try:
                device_setup.setup_app(app_class, env)
                if trial_logger is not None:
                    trial_logger.info(
                        "Re-initialized AndroidWorld app %s to recover a missing SQLite data path.",
                        app_name,
                    )
                return "setup_app"
            except Exception as error:
                if not _looks_like_androidworld_a11y_tree_failure(error) or setup_attempts >= 3:
                    if trial_logger is not None:
                        trial_logger.warning(
                            "AndroidWorld app setup retry for %s failed while recovering SQLite data: %s",
                            app_name,
                            error,
                        )
                    break
                _recover_androidworld_env_for_setup(env)

    launched = False
    try:
        adb_utils.launch_app(app_name, controller)
        launched = True
        time.sleep(7.0)
        if trial_logger is not None:
            trial_logger.info(
                "Launched AndroidWorld app %s once to recover a missing SQLite data path.",
                app_name,
            )
        return "launch_app"
    finally:
        if launched:
            with contextlib.suppress(Exception):
                adb_utils.close_app(app_name, controller)


def _patch_androidworld_sqlite_fts4_support(*, trial_logger: object | None = None) -> Callable[[], None]:
    if _python_sqlite_supports_fts4():
        return lambda: None

    sqlite3_cli = _find_sqlite3_cli()
    if not sqlite3_cli:
        if trial_logger is not None:
            trial_logger.warning(
                "AndroidWorld worker Python lacks SQLite FTS4 support and no sqlite3 CLI was found in PATH."
            )
        return lambda: None

    _require_runtime_import(
        "android_world.task_evals.utils.sqlite_utils",
        install_hint="python -m pip install -r references/benchmarks/android_world/requirements.txt",
    )
    from android_world.env import adb_utils
    from android_world.task_evals.utils import sqlite_schema_utils, sqlite_utils
    from android_world.utils import file_utils

    original_execute_query = sqlite_utils.execute_query
    original_get_rows_from_remote_device = sqlite_utils.get_rows_from_remote_device
    original_delete_all_rows_from_table = sqlite_utils.delete_all_rows_from_table
    original_insert_rows_to_remote_db = sqlite_utils.insert_rows_to_remote_db

    def execute_query_with_cli_fallback(query: str, db_path: str, row_type: type[object]) -> list[object]:
        try:
            return original_execute_query(query, db_path, row_type)
        except Exception as error:
            if not _sqlite_cli_fallback_required(error):
                raise
            payload = _run_sqlite3_cli(
                sqlite3_path=sqlite3_cli,
                db_path=db_path,
                sql=query,
                json_output=True,
            ).strip()
            raw_rows = json.loads(payload or "[]")
            if not isinstance(raw_rows, list):
                raise RuntimeError("sqlite3 CLI did not return a JSON row list.")
            return [row_type(**dict(row)) for row in raw_rows]

    def get_rows_from_remote_device_with_cli_fallback(
        table_name: str,
        remote_db_file_path: str,
        row_type: type[object],
        env: object,
        timeout_sec: float | None = None,
        n_retries: int = 3,
    ) -> list[object]:
        with env.controller.pull_file(remote_db_file_path, timeout_sec) as local_db_directory:
            local_db_path = file_utils.convert_to_posix_path(
                local_db_directory,
                os.path.split(remote_db_file_path)[1],
            )
            for _ in range(n_retries):
                try:
                    return execute_query_with_cli_fallback(
                        f"SELECT * FROM {table_name};",
                        local_db_path,
                        row_type,
                    )
                except Exception:
                    time.sleep(1.0)
        raise ValueError(
            f"Failed to retrieve rows from {table_name} from {remote_db_file_path} "
            f"after {n_retries} retries. Try increasing the number of retries."
        )

    def delete_all_rows_from_table_with_cli_fallback(
        table_name: str,
        remote_db_file_path: str,
        env: object,
        app_name: str,
        timeout_sec: float | None = None,
    ) -> None:
        try:
            return original_delete_all_rows_from_table(
                table_name,
                remote_db_file_path,
                env,
                app_name,
                timeout_sec,
            )
        except Exception as error:
            if _sqlite_missing_table_error(error) or _sqlite_missing_db_path_error(error):
                _initialize_androidworld_sqlite_owner_app(
                    app_name=app_name,
                    env=env,
                    trial_logger=trial_logger,
                )
                try:
                    return original_delete_all_rows_from_table(
                        table_name,
                        remote_db_file_path,
                        env,
                        app_name,
                        timeout_sec,
                    )
                except Exception as retry_error:
                    if _sqlite_missing_table_error(retry_error) or _sqlite_missing_db_path_error(retry_error):
                        with contextlib.suppress(Exception):
                            adb_utils.close_app(app_name, env.controller)
                        return None
                    if not _sqlite_cli_fallback_required(retry_error):
                        raise
            elif not _sqlite_cli_fallback_required(error):
                raise
        if not sqlite_utils.table_exists(table_name, remote_db_file_path, env):
            _initialize_androidworld_sqlite_owner_app(
                app_name=app_name,
                env=env,
                trial_logger=trial_logger,
            )
        try:
            with env.controller.pull_file(remote_db_file_path, timeout_sec) as local_db_directory:
                local_db_path = file_utils.convert_to_posix_path(
                    local_db_directory,
                    os.path.split(remote_db_file_path)[1],
                )
                _run_sqlite3_cli(
                    sqlite3_path=sqlite3_cli,
                    db_path=local_db_path,
                    sql=f"DELETE FROM {table_name};",
                )
                env.controller.push_file(local_db_path, remote_db_file_path, timeout_sec)
                adb_utils.close_app(app_name, env.controller)
        except Exception as error:
            if _sqlite_missing_db_path_error(error):
                return None
            raise

    def insert_rows_to_remote_db_with_cli_fallback(
        rows: list[object],
        exclude_key: str | None,
        table_name: str,
        remote_db_file_path: str,
        app_name: str,
        env: object,
        timeout_sec: float | None = None,
    ) -> None:
        try:
            return original_insert_rows_to_remote_db(
                rows,
                exclude_key,
                table_name,
                remote_db_file_path,
                app_name,
                env,
                timeout_sec,
            )
        except Exception as error:
            if _sqlite_missing_table_error(error) or _sqlite_missing_db_path_error(error):
                _initialize_androidworld_sqlite_owner_app(
                    app_name=app_name,
                    env=env,
                    trial_logger=trial_logger,
                )
                return original_insert_rows_to_remote_db(
                    rows,
                    exclude_key,
                    table_name,
                    remote_db_file_path,
                    app_name,
                    env,
                    timeout_sec,
                )
            if not _sqlite_cli_fallback_required(error):
                raise
        try:
            with env.controller.pull_file(remote_db_file_path, timeout_sec) as local_db_directory:
                local_db_path = file_utils.convert_to_posix_path(
                    local_db_directory,
                    os.path.split(remote_db_file_path)[1],
                )
                statements = ["BEGIN;"]
                statements.extend(
                    _sqlite_insert_statement(
                        row=row,
                        table_name=table_name,
                        exclude_key=exclude_key,
                    )
                    for row in rows
                )
                statements.append("COMMIT;")
                _run_sqlite3_cli(
                    sqlite3_path=sqlite3_cli,
                    db_path=local_db_path,
                    sql="\n".join(statements),
                )
                env.controller.push_file(local_db_path, remote_db_file_path, timeout_sec)
                adb_utils.close_app(app_name, env.controller)
        except Exception as error:
            if _sqlite_missing_db_path_error(error):
                _initialize_androidworld_sqlite_owner_app(
                    app_name=app_name,
                    env=env,
                    trial_logger=trial_logger,
                )
                return original_insert_rows_to_remote_db(
                    rows,
                    exclude_key,
                    table_name,
                    remote_db_file_path,
                    app_name,
                    env,
                    timeout_sec,
                )
            raise

    sqlite_utils.execute_query = execute_query_with_cli_fallback
    sqlite_utils.get_rows_from_remote_device = get_rows_from_remote_device_with_cli_fallback
    sqlite_utils.delete_all_rows_from_table = delete_all_rows_from_table_with_cli_fallback
    sqlite_utils.insert_rows_to_remote_db = insert_rows_to_remote_db_with_cli_fallback
    if trial_logger is not None:
        trial_logger.info(
            "Enabled sqlite3 CLI fallback for AndroidWorld because the configured worker Python lacks SQLite FTS4 support."
        )

    def restore() -> None:
        sqlite_utils.execute_query = original_execute_query
        sqlite_utils.get_rows_from_remote_device = original_get_rows_from_remote_device
        sqlite_utils.delete_all_rows_from_table = original_delete_all_rows_from_table
        sqlite_utils.insert_rows_to_remote_db = original_insert_rows_to_remote_db

    return restore


def _setup_task_scoped_apps(
    *,
    task_type: object,
    env: object,
    install_hint: str,
    adb_path: str | None = None,
    adb_serial: str | None = None,
    trial_logger: object | None = None,
) -> tuple[str, ...]:
    _require_runtime_import(
        "android_world.env.setup_device.setup",
        install_hint=install_hint,
    )
    from android_world.env import adb_utils
    from android_world.env.setup_device import setup as device_setup

    # Some AndroidWorld tasks populate app_names on the instantiated task rather
    # than the task class (for example information_retrieval/Joplin tasks).
    raw_app_names = getattr(task_type, "app_names", ()) or ()
    app_names = tuple(
        app_name.strip()
        for app_name in raw_app_names
        if isinstance(app_name, str) and app_name.strip()
    )
    app_names = _augment_androidworld_task_setup_app_names(app_names)

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
        package_name = ""
        package_name_getter = getattr(app_class, "package_name", None)
        if callable(package_name_getter):
            with contextlib.suppress(Exception):
                package_name = str(package_name_getter() or "").strip()

        is_package_installed = getattr(device_setup, "is_package_installed", None)
        already_installed = False
        if package_name and callable(is_package_installed):
            with contextlib.suppress(Exception):
                already_installed = bool(is_package_installed(package_name, env))

        if already_installed:
            if trial_logger is not None:
                trial_logger.info(
                    "AndroidWorld task app %s (%s) already exists on %s; skipping APK re-download.",
                    app_name,
                    package_name,
                    adb_serial or "device",
                )
        else:
            try:
                device_setup.maybe_install_app(app_class, env)
            except Exception as error:
                package_installed_after_failure = False
                if package_name and callable(is_package_installed):
                    with contextlib.suppress(Exception):
                        package_installed_after_failure = bool(is_package_installed(package_name, env))
                if package_installed_after_failure:
                    if trial_logger is not None:
                        trial_logger.info(
                            "AndroidWorld task app %s (%s) is present after a failed install attempt; continuing.",
                            app_name,
                            package_name,
                        )
                elif _looks_like_androidworld_task_app_install_failure(error):
                    raise RuntimeError(
                        "ANDROIDWORLD_APP_INSTALL_ERROR: failed to download or install the AndroidWorld task app "
                        f"'{app_name}'. If this emulator was prepared before, reuse it so the already-installed "
                        "package can be reused; otherwise allow HTTPS access to "
                        "storage.googleapis.com/gresearch/android_world or run `snowl-mobile benchmark-setup ...` "
                        f"once from a network-ready environment. Original error: {error}"
                    ) from error
                else:
                    raise
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
                if adb_path and adb_serial:
                    _ensure_androidworld_accessibility_runtime(
                        adb_path=adb_path,
                        adb_serial=adb_serial,
                        trial_logger=trial_logger,
                        env=env,
                        force_reconfigure=True,
                    )
        installed_apps.append(app_name)
    return tuple(installed_apps)


def _augment_androidworld_task_setup_app_names(app_names: tuple[str, ...]) -> tuple[str, ...]:
    expanded = list(app_names)
    seen = {name for name in expanded if isinstance(name, str)}
    # AndroidWorld SMS tasks pre-populate contacts through the Contacts insert
    # flow, but many task classes only declare the SMS app itself. Prepping the
    # Contacts app first avoids first-launch UI from breaking contact creation.
    if "simple sms messenger" in seen and "contacts" not in seen:
        expanded.append("contacts")
    return tuple(expanded)


def _looks_like_androidworld_a11y_tree_failure(error: Exception | str) -> bool:
    lowered = str(error).lower()
    return "could not get a11y tree" in lowered or "accessibility tree" in lowered


def _looks_like_androidworld_task_bootstrap_ui_failure(error: Exception | str) -> bool:
    lowered = str(error).lower()
    return (
        _looks_like_androidworld_a11y_tree_failure(error)
        or ("target text" in lowered and "not found" in lowered)
        or "invalid element index" in lowered
    )


def _looks_like_androidworld_task_app_install_failure(error: Exception | str) -> bool:
    lowered = str(error).lower()
    return (
        "failed to download and install apk" in lowered
        or "failed to download file_name from https://storage.googleapis.com/gresearch/android_world" in lowered
        or ("requests.exceptions" in lowered and "storage.googleapis.com/gresearch/android_world" in lowered)
    )


def _recover_androidworld_env_for_setup(env: object) -> None:
    controller = getattr(env, "controller", None)
    if controller is None:
        return
    refresh = getattr(controller, "refresh_env", None)
    if callable(refresh):
        refresh()
    from android_world.env import adb_utils

    adb_utils.press_home_button(controller)
    adb_utils.set_root_if_needed(controller)
    time.sleep(1.0)


def _find_androidworld_a11y_wrapper(env: object | None) -> object | None:
    candidates: list[object] = []
    if env is not None:
        candidates.append(env)
        controller = getattr(env, "controller", None)
        if controller is not None:
            candidates.append(controller)
            controller_env = getattr(controller, "env", None)
            if controller_env is not None:
                candidates.append(controller_env)

    for candidate in candidates:
        current = candidate
        seen: set[int] = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            if all(
                callable(getattr(current, name, None))
                for name in ("_start_a11y_services", "_enable_a11y_tree_logs", "_configure_grpc")
            ):
                return current
            current = getattr(current, "_env", None)
    return None


def _reconfigure_androidworld_a11y_wrapper(
    *,
    env: object | None,
    trial_logger: object | None,
) -> None:
    wrapper = _find_androidworld_a11y_wrapper(env)
    if wrapper is None:
        return

    start_services = getattr(wrapper, "_start_a11y_services", None)
    enable_tree_logs = getattr(wrapper, "_enable_a11y_tree_logs", None)
    configure_grpc = getattr(wrapper, "_configure_grpc", None)

    if callable(start_services):
        start_services()
        time.sleep(1.0)
    if callable(enable_tree_logs):
        enable_tree_logs()
    if callable(configure_grpc):
        configure_grpc()
    time.sleep(1.0)

    if trial_logger is not None:
        trial_logger.info("Reconfigured AndroidWorld accessibility runtime.")


def _run_androidworld_env_operation(
    *,
    env_ref: dict[str, object],
    trial_logger: object,
    description: str,
    operation: Callable[[], _T],
    reload_env: Callable[[], object] | None = None,
    max_attempts: int = 3,
) -> _T:
    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except Exception as error:
            if not _looks_like_androidworld_a11y_tree_failure(error):
                raise
            if attempt >= max_attempts:
                raise RuntimeError(
                    "ANDROIDWORLD_ENV_ERROR: AndroidWorld accessibility runtime became unavailable during "
                    f"{description}. The emulator may be unhealthy; restart the AVD and then resume with the same "
                    f"output directory. Original error: {error}"
                ) from error
            if trial_logger is not None:
                trial_logger.warning(
                    "AndroidWorld accessibility runtime failed during %s (attempt %s/%s); refreshing the env and retrying.",
                    description,
                    attempt,
                    max_attempts,
                )
            if reload_env is not None:
                env_ref["env"] = reload_env()
            else:
                _recover_androidworld_env_for_setup(env_ref["env"])
    raise AssertionError("unreachable")


def _run_androidworld_task_bootstrap_with_recovery(
    *,
    env_ref: dict[str, object],
    trial_logger: object,
    task_name: str,
    bootstrap_operation: Callable[[], _T],
    refresh_bootstrap_state: Callable[[], None] | None = None,
    reload_env: Callable[[], object] | None = None,
    max_attempts: int = 2,
) -> _T:
    for attempt in range(1, max_attempts + 1):
        try:
            return _run_androidworld_env_operation(
                env_ref=env_ref,
                trial_logger=trial_logger,
                description=f"task bootstrap for '{task_name}'",
                operation=bootstrap_operation,
                reload_env=reload_env,
            )
        except Exception as error:
            if not _looks_like_androidworld_task_bootstrap_ui_failure(error) or attempt >= max_attempts:
                raise
            if trial_logger is not None:
                trial_logger.warning(
                    "AndroidWorld task bootstrap for %s failed with a recoverable UI/setup error (%s/%s): %s. Refreshing the env and retrying once.",
                    task_name,
                    attempt,
                    max_attempts,
                    error,
                )
            if reload_env is not None:
                env_ref["env"] = reload_env()
            else:
                _recover_androidworld_env_for_setup(env_ref["env"])
            if refresh_bootstrap_state is not None:
                refresh_bootstrap_state()
    raise AssertionError("unreachable")


def _decode_androidworld_generic_output(response: object) -> str:
    generic = getattr(response, "generic", None)
    output = getattr(generic, "output", b"")
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return str(output or "")


def _query_androidworld_raw_contact_ids(*, adb_utils_module: object, env: object) -> tuple[int, ...]:
    response = adb_utils_module.issue_generic_request(
        ["shell", "content", "query", "--uri", "content://com.android.contacts/raw_contacts"],
        env,
    )
    adb_utils_module.check_ok(response, "Failed to query AndroidWorld raw contacts.")
    output = _decode_androidworld_generic_output(response)
    contact_ids = [int(match.group(1)) for match in re.finditer(r"(?<!\d)_id=(\d+)", output)]
    return tuple(contact_ids)


def _insert_androidworld_contact_via_provider(
    *,
    name: str,
    phone_number: str,
    env: object,
) -> dict[str, object]:
    adb_utils_module = importlib.import_module("android_world.env.adb_utils")
    contacts_utils_module = importlib.import_module("android_world.utils.contacts_utils")

    before_ids = set(_query_androidworld_raw_contact_ids(adb_utils_module=adb_utils_module, env=env))
    response = adb_utils_module.issue_generic_request(
        [
            "shell",
            "content",
            "insert",
            "--uri",
            "content://com.android.contacts/raw_contacts",
            "--bind",
            "account_type:s:",
            "--bind",
            "account_name:s:",
        ],
        env,
    )
    adb_utils_module.check_ok(response, "Failed to create AndroidWorld raw contact via content provider.")
    time.sleep(0.5)

    after_ids = set(_query_androidworld_raw_contact_ids(adb_utils_module=adb_utils_module, env=env))
    candidate_ids = sorted(after_ids - before_ids) or sorted(after_ids)
    if not candidate_ids:
        raise RuntimeError("AndroidWorld contact provider fallback could not resolve a raw contact id.")
    raw_contact_id = candidate_ids[-1]

    provider_commands = (
        [
            "shell",
            "content",
            "insert",
            "--uri",
            "content://com.android.contacts/data",
            "--bind",
            f"raw_contact_id:i:{raw_contact_id}",
            "--bind",
            "mimetype:s:vnd.android.cursor.item/name",
            "--bind",
            f"data1:s:{name}",
        ],
        [
            "shell",
            "content",
            "insert",
            "--uri",
            "content://com.android.contacts/data",
            "--bind",
            f"raw_contact_id:i:{raw_contact_id}",
            "--bind",
            "mimetype:s:vnd.android.cursor.item/phone_v2",
            "--bind",
            f"data1:s:{phone_number}",
            "--bind",
            "data2:i:2",
        ],
    )
    for command in provider_commands:
        response = adb_utils_module.issue_generic_request(command, env)
        adb_utils_module.check_ok(response, "Failed to populate AndroidWorld contact data via content provider.")
    time.sleep(0.5)

    normalized_phone = str(contacts_utils_module.clean_phone_number(phone_number))
    contacts = contacts_utils_module.list_contacts(env)
    if not any(str(getattr(contact, "number", "")).strip() == normalized_phone for contact in contacts):
        raise RuntimeError(
            "AndroidWorld contact provider fallback inserted a contact row, but the phone number did not become "
            "visible in the Contacts provider."
        )

    return {
        "method": "content_provider_insert",
        "raw_contact_id": raw_contact_id,
        "normalized_phone": normalized_phone,
    }


@contextlib.contextmanager
def _patch_androidworld_contact_insert_fallback(*, trial_logger: object | None):
    try:
        contacts_utils_module = importlib.import_module("android_world.utils.contacts_utils")
    except ModuleNotFoundError:
        yield
        return
    original_add_contact = contacts_utils_module.add_contact

    def patched_add_contact(
        name: str,
        phone_number: str,
        env: object,
        ui_delay_sec: float = 1.0,
    ) -> object:
        try:
            return original_add_contact(name, phone_number, env, ui_delay_sec)
        except Exception as error:
            if not _looks_like_androidworld_task_bootstrap_ui_failure(error):
                raise
            if trial_logger is not None:
                trial_logger.warning(
                    "AndroidWorld UI-based contact insertion failed for %r (%s); falling back to content provider "
                    "insertion.",
                    name,
                    error,
                )
            fallback_details = _insert_androidworld_contact_via_provider(
                name=name,
                phone_number=phone_number,
                env=env,
            )
            if trial_logger is not None:
                trial_logger.info(
                    "Inserted AndroidWorld contact %r via %s (raw_contact_id=%s).",
                    name,
                    fallback_details["method"],
                    fallback_details["raw_contact_id"],
                )
            return None

    contacts_utils_module.add_contact = patched_add_contact
    try:
        yield
    finally:
        contacts_utils_module.add_contact = original_add_contact


def _initialize_androidworld_task_with_contact_fallback(
    *,
    task: object,
    env: object,
    trial_logger: object | None,
) -> None:
    with _patch_androidworld_contact_insert_fallback(trial_logger=trial_logger):
        task.initialize_task(env)


def _collect_androidworld_task_app_names(task: object) -> tuple[str, ...]:
    raw_app_names: list[object] = []
    for candidate in (getattr(task, "app_names", ()), getattr(type(task), "app_names", ())):
        if isinstance(candidate, str):
            raw_app_names.append(candidate)
        elif isinstance(candidate, (list, tuple, set)):
            raw_app_names.extend(candidate)

    app_names: list[str] = []
    seen: set[str] = set()
    for item in raw_app_names:
        if not isinstance(item, str):
            continue
        name = item.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        app_names.append(name)
    return tuple(app_names)


def _initialize_androidworld_task_apps_for_scoring(
    *,
    task: object,
    env: object,
    trial_logger: object | None = None,
) -> tuple[str, ...]:
    controller = getattr(env, "controller", None)
    if controller is None:
        return ()

    app_names = _collect_androidworld_task_app_names(task)
    if not app_names:
        return ()

    _require_runtime_import(
        "android_world.env.adb_utils",
        install_hint="python -m pip install -r references/benchmarks/android_world/requirements.txt",
    )
    from android_world.env import adb_utils

    with contextlib.suppress(Exception):
        adb_utils.press_home_button(controller)
    with contextlib.suppress(Exception):
        adb_utils.set_root_if_needed(controller)

    initialized_apps: list[str] = []
    for app_name in app_names:
        launched = False
        try:
            adb_utils.launch_app(app_name, controller)
            launched = True
            time.sleep(7.0)
            initialized_apps.append(app_name)
            if trial_logger is not None:
                trial_logger.info(
                    "Launched AndroidWorld task app %s once before retrying native scoring.",
                    app_name,
                )
        except Exception as error:
            if trial_logger is not None:
                trial_logger.warning(
                    "Failed to launch AndroidWorld task app %s while recovering native scoring: %s",
                    app_name,
                    error,
                )
        finally:
            if launched:
                with contextlib.suppress(Exception):
                    adb_utils.close_app(app_name, controller)

    with contextlib.suppress(Exception):
        adb_utils.press_home_button(controller)
    return tuple(initialized_apps)


def _score_androidworld_task_with_missing_table_recovery(
    *,
    task: object,
    task_name: str,
    env_ref: dict[str, object],
    trial_logger: object,
    reload_env: Callable[[], object] | None = None,
    notes: list[str] | None = None,
) -> float:
    def _score_once() -> float:
        return float(
            _run_androidworld_env_operation(
                env_ref=env_ref,
                trial_logger=trial_logger,
                description=f"native scoring for '{task_name}'",
                operation=lambda: task.is_successful(env_ref["env"]),
                reload_env=reload_env,
            )
        )

    try:
        return _score_once()
    except Exception as error:
        if not (_sqlite_missing_table_error(error) or _sqlite_missing_db_path_error(error)):
            raise

    if trial_logger is not None:
        trial_logger.warning(
            "AndroidWorld native scoring for %s hit an uninitialized SQLite database; launching the task apps once and retrying.",
            task_name,
        )
    initialized_apps = _initialize_androidworld_task_apps_for_scoring(
        task=task,
        env=env_ref["env"],
        trial_logger=trial_logger,
    )
    if notes is not None:
        if initialized_apps:
            notes.append(
                "AndroidWorld native scorer hit an uninitialized app database; the bridge launched "
                f"{', '.join(initialized_apps)} once and retried scoring."
            )
        else:
            notes.append(
                "AndroidWorld native scorer hit an uninitialized app database; the bridge retried scoring "
                "after a lightweight recovery attempt."
            )

    try:
        return _score_once()
    except Exception as retry_error:
        if not (_sqlite_missing_table_error(retry_error) or _sqlite_missing_db_path_error(retry_error)):
            raise
        if trial_logger is not None:
            trial_logger.warning(
                "AndroidWorld native scoring for %s still reports a missing SQLite database after recovery; recording the task as unsuccessful instead of crashing the trial.",
                task_name,
            )
        if notes is not None:
            notes.append(
                "AndroidWorld native scorer still could not read an app-owned SQLite database after recovery, so the "
                "bridge recorded this task as unsuccessful instead of failing the whole trial."
            )
        return 0.0


def _clean_reasoning_text(text: str | None) -> str | None:
    if text is None:
        return None
    content = str(text).strip()
    for marker in ("<think>", "</think>", "<answer>", "</answer>"):
        content = content.replace(marker, "")
    cleaned = content.strip()
    return cleaned or None


def _clean_action_text(text: str | None) -> str | None:
    if text is None:
        return None
    content = str(text).strip()
    if "<answer>" in content:
        content = content.split("<answer>", 1)[1]
    if "</answer>" in content:
        content = content.split("</answer>", 1)[0]
    cleaned = content.strip()
    return cleaned or None


def _escape_adb_input_text(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(" ", "%s")
        .replace("&", "\\&")
        .replace("|", "\\|")
        .replace("<", "\\<")
        .replace(">", "\\>")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace(";", "\\;")
        .replace('"', '\\"')
        .replace("'", "\\'")
    )


def _run_adb(
    *,
    adb_path: str,
    adb_serial: str,
    argv: list[str],
    timeout_sec: float = 30.0,
) -> subprocess.CompletedProcess[str]:
    command = [adb_path]
    if adb_serial:
        command.extend(["-s", adb_serial])
    command.extend(argv)
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        check=False,
    )


def _android_package_installed(
    *,
    adb_path: str,
    adb_serial: str,
    package_name: str,
) -> bool:
    result = _run_adb(
        adb_path=adb_path,
        adb_serial=adb_serial,
        argv=["shell", "pm", "path", package_name],
    )
    output = f"{result.stdout}\n{result.stderr}".lower()
    return result.returncode == 0 and "package:" in output


def _adb_text(result: subprocess.CompletedProcess[str]) -> str:
    return f"{result.stdout}\n{result.stderr}".strip()


def _android_getprop(
    *,
    adb_path: str,
    adb_serial: str,
    name: str,
) -> str:
    result = _run_adb(
        adb_path=adb_path,
        adb_serial=adb_serial,
        argv=["shell", "getprop", name],
    )
    if result.returncode != 0:
        return ""
    return _adb_text(result).strip()


def _android_get_secure_setting(
    *,
    adb_path: str,
    adb_serial: str,
    key: str,
) -> str:
    result = _run_adb(
        adb_path=adb_path,
        adb_serial=adb_serial,
        argv=["shell", "settings", "get", "secure", key],
    )
    if result.returncode != 0:
        return ""
    return _adb_text(result).strip()


def _android_put_secure_setting(
    *,
    adb_path: str,
    adb_serial: str,
    key: str,
    value: str,
) -> bool:
    result = _run_adb(
        adb_path=adb_path,
        adb_serial=adb_serial,
        argv=["shell", "settings", "put", "secure", key, value],
    )
    return result.returncode == 0


def _android_delete_secure_setting(
    *,
    adb_path: str,
    adb_serial: str,
    key: str,
) -> bool:
    result = _run_adb(
        adb_path=adb_path,
        adb_serial=adb_serial,
        argv=["shell", "settings", "delete", "secure", key],
    )
    return result.returncode == 0


def _android_force_stop_package(
    *,
    adb_path: str,
    adb_serial: str,
    package_name: str,
) -> bool:
    result = _run_adb(
        adb_path=adb_path,
        adb_serial=adb_serial,
        argv=["shell", "am", "force-stop", package_name],
    )
    return result.returncode == 0


def _android_get_accessibility_runtime_status(
    *,
    adb_path: str,
    adb_serial: str,
) -> dict[str, bool]:
    result = _run_adb(
        adb_path=adb_path,
        adb_serial=adb_serial,
        argv=["shell", "dumpsys", "accessibility"],
        timeout_sec=30.0,
    )
    text = _adb_text(result)
    lines = [line.strip() for line in text.splitlines()]
    enabled = False
    bound = False
    binding = False
    crashed = False
    for line in lines:
        if line.startswith("Enabled services:"):
            enabled = _ANDROIDWORLD_A11Y_FORWARDER_SERVICE in line
        elif line.startswith("Bound services:"):
            bound = _ANDROIDWORLD_A11Y_FORWARDER_SERVICE in line
        elif line.startswith("Binding services:"):
            binding = _ANDROIDWORLD_A11Y_FORWARDER_SERVICE in line
        elif line.startswith("Crashed services:"):
            crashed = _ANDROIDWORLD_A11Y_FORWARDER_SERVICE in line
    return {
        "enabled": enabled,
        "bound": bound,
        "binding": binding,
        "crashed": crashed,
        "raw_text": text,
    }


def _probe_androidworld_device_profile(
    *,
    adb_path: str,
    adb_serial: str,
) -> dict[str, str]:
    return {
        "avd_name": _android_getprop(adb_path=adb_path, adb_serial=adb_serial, name="ro.boot.qemu.avd_name"),
        "sdk_int": _android_getprop(adb_path=adb_path, adb_serial=adb_serial, name="ro.build.version.sdk"),
        "android_release": _android_getprop(adb_path=adb_path, adb_serial=adb_serial, name="ro.build.version.release"),
        "product_model": _android_getprop(adb_path=adb_path, adb_serial=adb_serial, name="ro.product.model"),
    }


def _warn_if_androidworld_device_profile_unsupported(
    *,
    adb_path: str,
    adb_serial: str,
    trial_logger: object | None,
) -> dict[str, str]:
    profile = _probe_androidworld_device_profile(adb_path=adb_path, adb_serial=adb_serial)
    sdk_int = profile.get("sdk_int", "").strip()
    if sdk_int and sdk_int != "33" and trial_logger is not None:
        trial_logger.warning(
            "AndroidWorld upstream recommends an Android 13 / API 33 AVD (README: Pixel 6, Tiramisu). "
            "Current emulator reports sdk=%s release=%s avd=%s model=%s. This mismatch can make the "
            "accessibility forwarder unstable and lead to 'Could not get a11y tree' failures.",
            sdk_int or "<unknown>",
            profile.get("android_release", "") or "<unknown>",
            profile.get("avd_name", "") or "<unknown>",
            profile.get("product_model", "") or "<unknown>",
        )
    return profile


def _ensure_androidworld_accessibility_runtime(
    *,
    adb_path: str,
    adb_serial: str,
    trial_logger: object | None,
    env: object | None = None,
    force_reconfigure: bool = False,
) -> None:
    if not _android_package_installed(
        adb_path=adb_path,
        adb_serial=adb_serial,
        package_name=_ANDROIDWORLD_A11Y_FORWARDER_PACKAGE,
    ):
        return

    enabled_services = _android_get_secure_setting(
        adb_path=adb_path,
        adb_serial=adb_serial,
        key="enabled_accessibility_services",
    )
    accessibility_enabled = _android_get_secure_setting(
        adb_path=adb_path,
        adb_serial=adb_serial,
        key="accessibility_enabled",
    )
    if (
        _ANDROIDWORLD_A11Y_FORWARDER_SERVICE in enabled_services
        and accessibility_enabled == "1"
    ):
        if env is not None and force_reconfigure:
            _reconfigure_androidworld_a11y_wrapper(env=env, trial_logger=trial_logger)
    else:
        if trial_logger is not None:
            trial_logger.info(
                "AndroidWorld accessibility runtime looked disabled on %s "
                "(enabled_accessibility_services=%s accessibility_enabled=%s); re-enabling it.",
                adb_serial,
                enabled_services or "<empty>",
                accessibility_enabled or "<empty>",
            )

        merged_services = ":".join(
            service
            for service in dict.fromkeys(
                [
                    part.strip()
                    for part in [*enabled_services.split(":"), _ANDROIDWORLD_A11Y_FORWARDER_SERVICE]
                    if isinstance(part, str)
                ]
            )
            if service
        )
        _android_put_secure_setting(
            adb_path=adb_path,
            adb_serial=adb_serial,
            key="enabled_accessibility_services",
            value=merged_services or _ANDROIDWORLD_A11Y_FORWARDER_SERVICE,
        )
        _android_put_secure_setting(
            adb_path=adb_path,
            adb_serial=adb_serial,
            key="accessibility_enabled",
            value="1",
        )
        time.sleep(1.0)
        if env is not None:
            _reconfigure_androidworld_a11y_wrapper(env=env, trial_logger=trial_logger)

    confirmed_enabled = _android_get_secure_setting(
        adb_path=adb_path,
        adb_serial=adb_serial,
        key="accessibility_enabled",
    )
    if confirmed_enabled != "1" and trial_logger is not None:
        trial_logger.warning(
            "AndroidWorld accessibility service was re-enabled on %s, but the device still reports "
            "accessibility_enabled=%s. If a11y tree failures persist, rebuild the AVD as Android 13 / API 33 "
            "and run `snowl-mobile benchmark-setup ...` once.",
            adb_serial,
            confirmed_enabled or "<empty>",
        )

    runtime_status = _android_get_accessibility_runtime_status(
        adb_path=adb_path,
        adb_serial=adb_serial,
    )
    if runtime_status["bound"] and not runtime_status["crashed"]:
        return

    if trial_logger is not None:
        trial_logger.warning(
            "AndroidWorld accessibility service on %s was not bound cleanly "
            "(enabled=%s bound=%s binding=%s crashed=%s); restarting the forwarder service.",
            adb_serial,
            runtime_status["enabled"],
            runtime_status["bound"],
            runtime_status["binding"],
            runtime_status["crashed"],
        )

    _android_force_stop_package(
        adb_path=adb_path,
        adb_serial=adb_serial,
        package_name=_ANDROIDWORLD_A11Y_FORWARDER_PACKAGE,
    )
    _android_delete_secure_setting(
        adb_path=adb_path,
        adb_serial=adb_serial,
        key="enabled_accessibility_services",
    )
    _android_put_secure_setting(
        adb_path=adb_path,
        adb_serial=adb_serial,
        key="accessibility_enabled",
        value="0",
    )
    time.sleep(1.0)
    _android_put_secure_setting(
        adb_path=adb_path,
        adb_serial=adb_serial,
        key="enabled_accessibility_services",
        value=_ANDROIDWORLD_A11Y_FORWARDER_SERVICE,
    )
    _android_put_secure_setting(
        adb_path=adb_path,
        adb_serial=adb_serial,
        key="accessibility_enabled",
        value="1",
    )
    if env is not None:
        _reconfigure_androidworld_a11y_wrapper(env=env, trial_logger=trial_logger)
    time.sleep(2.0)

    runtime_status = _android_get_accessibility_runtime_status(
        adb_path=adb_path,
        adb_serial=adb_serial,
    )
    if (
        not runtime_status["bound"]
        and not runtime_status["binding"]
        and trial_logger is not None
    ):
        trial_logger.warning(
            "AndroidWorld accessibility service still is not bound on %s after restart "
            "(enabled=%s crashed=%s). The emulator may need a manual reboot.",
            adb_serial,
            runtime_status["enabled"],
            runtime_status["crashed"],
        )


def _looks_like_model_endpoint_failure(text: str) -> bool:
    lowered = text.lower()
    strong_markers = (
        "openai.apiconnectionerror",
        "httpx.connecterror",
        "httpcore.connecterror",
        "ssl: unexpected_eof_while_reading",
        "certificate verify failed",
        "model error: connection error",
        "connection error.",
        "timed out",
        "read timeout",
        "connect timeout",
    )
    if any(marker in lowered for marker in strong_markers):
        return True
    return (
        "openai" in lowered
        and "connection" in lowered
        and ("ssl" in lowered or "httpx" in lowered or "httpcore" in lowered)
    )


def _looks_like_a11y_forwarder_download_failure(text: str) -> bool:
    lowered = text.lower()
    return (
        "accessibility forwarder" in lowered
        or "accessibility_forwarder.apk" in lowered
        or "storage.googleapis.com/android_env-tasks" in lowered
        or ("urlopen error" in lowered and "ssl" in lowered)
    )


def _build_model_endpoint_error(detail: str) -> RuntimeError:
    compact_detail = _compact_log_text(detail, max_chars=260)
    detail_suffix = f" Detail: {compact_detail}" if compact_detail else ""
    return RuntimeError(
        "MODEL_API_ERROR: Open-AutoGLM could not reach the configured model endpoint. "
        "Check PHONE_AGENT_BASE_URL, PHONE_AGENT_API_KEY, PHONE_AGENT_MODEL, and any local proxy/SSL settings."
        f"{detail_suffix}"
    )


def _adb_keyboard_available(*, adb_path: str, adb_serial: str) -> bool:
    result = _run_adb(
        adb_path=adb_path,
        adb_serial=adb_serial,
        argv=["shell", "ime", "list", "-a"],
    )
    output = f"{result.stdout}\n{result.stderr}".lower()
    return "com.android.adbkeyboard/.adbime" in output


def _type_text_via_input_text(
    *,
    adb_path: str,
    adb_serial: str,
    text: str,
) -> tuple[bool, str]:
    escaped = _escape_adb_input_text(text)
    result = _run_adb(
        adb_path=adb_path,
        adb_serial=adb_serial,
        argv=["shell", "input", "text", escaped],
    )
    if result.returncode == 0:
        return True, "Typed text via adb shell input text."
    return (
        False,
        "adb shell input text failed: "
        + json.dumps(
            {
                "returncode": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
    )


def _press_enter_via_keyevent(
    *,
    adb_path: str,
    adb_serial: str,
) -> tuple[bool, str]:
    result = _run_adb(
        adb_path=adb_path,
        adb_serial=adb_serial,
        argv=["shell", "input", "keyevent", "66"],
    )
    if result.returncode == 0:
        return True, "Pressed Enter via adb shell input keyevent 66."
    return (
        False,
        "adb shell input keyevent failed: "
        + json.dumps(
            {
                "returncode": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
    )


def _sanitize_model_response(response: object) -> object:
    cleaned_action = _clean_action_text(getattr(response, "action", None))
    cleaned_thinking = _clean_reasoning_text(getattr(response, "thinking", None))
    if cleaned_action is not None:
        setattr(response, "action", cleaned_action)
    if cleaned_thinking is not None:
        setattr(response, "thinking", cleaned_thinking)
    return response


def _patch_action_coordinate_conversion(phone_agent: object) -> callable:
    handler = phone_agent.action_handler
    original_converter = handler._convert_relative_to_absolute

    def patched_converter(
        element: list[int],
        screen_width: int,
        screen_height: int,
    ) -> tuple[int, int]:
        try:
            x = float(element[0])
            y = float(element[1])
        except Exception:
            return original_converter(element, screen_width, screen_height)
        absolute_x = max(0, min(int(round(x)), max(screen_width - 1, 0)))
        absolute_y = max(0, min(int(round(y)), max(screen_height - 1, 0)))
        return absolute_x, absolute_y

    handler._convert_relative_to_absolute = patched_converter

    def restore() -> None:
        handler._convert_relative_to_absolute = original_converter

    return restore


def _patch_launch_aliases(phone_agent: object) -> callable:
    handler = phone_agent.action_handler
    original_handle_launch = handler._handle_launch
    from phone_agent.config.apps import APP_PACKAGES

    aliases = {
        "".join(character.lower() for character in name if character.isalnum()): name
        for name in APP_PACKAGES
    }

    def patched_handle_launch(action: dict[str, object], width: int, height: int) -> object:
        app_name = str(action.get("app", "")).strip()
        if not app_name:
            return original_handle_launch(action, width, height)
        normalized = "".join(character.lower() for character in app_name if character.isalnum())
        mapped_name = aliases.get(normalized)
        if mapped_name is None:
            return original_handle_launch(action, width, height)
        updated_action = dict(action)
        updated_action["app"] = mapped_name
        return original_handle_launch(updated_action, width, height)

    handler._handle_launch = patched_handle_launch

    def restore() -> None:
        handler._handle_launch = original_handle_launch

    return restore


def _patch_type_input_fallback(
    phone_agent: object,
    *,
    adb_serial: str,
    adb_path: str,
) -> tuple[callable, str]:
    handler = phone_agent.action_handler
    original_handle_type = handler._handle_type
    adb_keyboard_ready = _adb_keyboard_available(adb_path=adb_path, adb_serial=adb_serial)

    def patched_handle_type(action: dict[str, object], width: int, height: int) -> object:
        if adb_keyboard_ready:
            return original_handle_type(action, width, height)
        from phone_agent.actions.handler import ActionResult

        text = str(action.get("text", "") or "")
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        if not normalized:
            return ActionResult(True, False, "Skipped empty text input.")
        messages: list[str] = []
        success = True
        parts = normalized.split("\n")
        for index, part in enumerate(parts):
            if part:
                ok, message = _type_text_via_input_text(
                    adb_path=adb_path,
                    adb_serial=adb_serial,
                    text=part,
                )
                success = success and ok
                messages.append(message)
                time.sleep(0.15)
            should_press_enter = index < len(parts) - 1 or normalized.endswith("\n")
            if should_press_enter:
                ok, message = _press_enter_via_keyevent(
                    adb_path=adb_path,
                    adb_serial=adb_serial,
                )
                success = success and ok
                messages.append(message)
                time.sleep(0.15)
        return ActionResult(success, False, "; ".join(messages))

    handler._handle_type = patched_handle_type

    def restore() -> None:
        handler._handle_type = original_handle_type

    backend_name = "adb_keyboard" if adb_keyboard_ready else "adb_shell_input_text_fallback"
    return restore, backend_name


def _write_ui_xml(
    path: Path,
    *,
    ui_elements: list[dict[str, object]],
    activity: str,
    package_name: str,
    screen_size: str,
) -> None:
    root = ET.Element("hierarchy")
    if activity:
        root.set("activity", activity)
    if package_name:
        root.set("package", package_name)
    if screen_size:
        root.set("screen_size", screen_size)
    attribute_map = {
        "text": "text",
        "content_description": "content-desc",
        "hint_text": "hint-text",
        "resource_id": "resource-id",
        "class_name": "class",
        "package_name": "package",
        "bounds": "bounds",
        "is_clickable": "clickable",
        "is_editable": "editable",
        "is_enabled": "enabled",
        "is_focused": "focused",
        "is_focusable": "focusable",
        "is_long_clickable": "long-clickable",
        "is_scrollable": "scrollable",
        "is_selected": "selected",
    }
    for index, element in enumerate(ui_elements):
        node = ET.SubElement(root, "node")
        node.set("index", str(index))
        for source_name, target_name in attribute_map.items():
            value = element.get(source_name)
            if value in (None, ""):
                continue
            if isinstance(value, bool):
                node.set(target_name, "true" if value else "false")
            else:
                node.set(target_name, str(value))
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _persist_observation(
    *,
    state: object,
    env: object,
    raw_dir: Path,
    trial_dir: Path,
) -> tuple[dict[str, object], dict[str, str]]:
    screenshot_path = raw_dir / "observation.ppm"
    ui_tree_path = raw_dir / "ui_tree.json"
    state_summary_path = raw_dir / "state_summary.json"
    raw_artifacts: dict[str, str] = {}

    _write_ppm(screenshot_path, getattr(state, "pixels"))
    raw_artifacts[f"{raw_dir.name}_screenshot"] = _relative_to_trial(screenshot_path, trial_dir=trial_dir)

    ui_elements = _serialize_ui_elements(list(getattr(state, "ui_elements", [])))
    _write_json(
        ui_tree_path,
        {
            "ui_element_count": len(ui_elements),
            "elements": ui_elements,
        },
    )
    raw_artifacts[f"{raw_dir.name}_ui_tree"] = _relative_to_trial(ui_tree_path, trial_dir=trial_dir)

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
    raw_artifacts[f"{raw_dir.name}_state_summary"] = _relative_to_trial(state_summary_path, trial_dir=trial_dir)

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


def _persist_platform_step_artifacts(
    *,
    step_index: int,
    state: object,
    env: object,
    trial_dir: Path,
    observation: dict[str, object],
) -> tuple[dict[str, object], dict[str, str]]:
    steps_dir = trial_dir / "steps"
    steps_dir.mkdir(parents=True, exist_ok=True)
    step_name = f"{step_index:04d}"
    screenshot_path = steps_dir / f"{step_name}.png"
    xml_path = steps_dir / f"{step_name}.xml"

    ui_elements = _serialize_ui_elements(list(getattr(state, "ui_elements", [])))
    _write_png(screenshot_path, getattr(state, "pixels"))
    _write_ui_xml(
        xml_path,
        ui_elements=ui_elements,
        activity=str(observation.get("activity") or ""),
        package_name=str(observation.get("package_name") or ""),
        screen_size=str(observation.get("screen_size") or ""),
    )

    updated_observation = dict(observation)
    updated_observation["screenshot_path"] = _relative_to_trial(screenshot_path, trial_dir=trial_dir)
    updated_observation["xml_path"] = _relative_to_trial(xml_path, trial_dir=trial_dir)
    return updated_observation, {
        f"platform_step_{step_name}_screenshot": _relative_to_trial(screenshot_path, trial_dir=trial_dir),
        f"platform_step_{step_name}_xml": _relative_to_trial(xml_path, trial_dir=trial_dir),
    }


def _step_payload(
    *,
    step_index: int,
    observation: dict[str, object],
    action_record: object,
    task_instruction: str,
    thinking: str | None,
    action_text: str | None,
    response_text_path: Path,
    response_json_path: Path,
    console_path: Path,
    persisted_at: str,
    trial_dir: Path,
) -> dict[str, object]:
    return {
        "step_index": step_index,
        "attempt": 1,
        "status": "completed",
        "observation": observation,
        "action": {
            "agent_raw_output": getattr(action_record, "agent_raw_output", None),
            "parsed_action": dict(getattr(action_record, "parsed_action", {})),
            "executed_action": dict(getattr(action_record, "executed_action", {})),
            "execution_result": dict(getattr(action_record, "execution_result", {})),
        },
        "artifacts": {
            "screenshot_path": observation.get("screenshot_path"),
            "xml_path": observation.get("xml_path"),
            "model_response_text_path": _relative_to_trial(response_text_path, trial_dir=trial_dir),
            "model_response_json_path": _relative_to_trial(response_json_path, trial_dir=trial_dir),
            "observation_path": _relative_to_trial(console_path, trial_dir=trial_dir),
        },
        "timestamps": {
            "observed_at": observation.get("timestamp") or persisted_at,
            "action_at": persisted_at,
            "persisted_at": persisted_at,
        },
        "task_instruction": task_instruction,
        "thought": thinking,
        "action_text": action_text,
        "action_input": dict(getattr(action_record, "parsed_action", {})),
        "notes": [
            "Open-AutoGLM x AndroidWorld runtime persisted this step from the pair-specific bridge subprocess.",
        ],
    }


def _compose_task_prompt(*, task_instruction: str, task_name: str) -> str:
    hints: list[str] = []
    if task_name.startswith("SimpleSms"):
        hints.append(
            'When you need to launch the SMS app, use `do(action="Launch", app="SimpleSMSMessenger")`.'
        )
    if not hints:
        return task_instruction
    return (
        f"{task_instruction}\n\n"
        "Runtime launch hints:\n"
        + "\n".join(f"- {hint}" for hint in hints)
    )


def _resolve_task_instruction(*, task: object, fallback_instruction: str, task_name: str) -> str:
    goal = str(getattr(task, "goal", "") or "").strip()
    if goal:
        return goal
    instruction = fallback_instruction.strip()
    if instruction:
        return instruction
    return f"Run AndroidWorld task '{task_name}'."


def _patch_androidworld_clear_directory(*, trial_logger: object) -> callable:
    from android_world.utils import file_utils

    original_clear_directory = file_utils.clear_directory

    def patched_clear_directory(directory_path: str, env: object) -> None:
        try:
            return original_clear_directory(directory_path, env)
        except Exception as error:
            error_text = str(error)
            if "No such file or directory" in error_text and "shell rm -r" in error_text:
                trial_logger.warning(
                    "AndroidWorld clear_directory tolerated a missing wildcard target for %s.",
                    directory_path,
                )
                return None
            raise

    file_utils.clear_directory = patched_clear_directory

    def restore() -> None:
        file_utils.clear_directory = original_clear_directory

    return restore


def _patch_androidworld_a11y_forwarder_install(
    *,
    adb_path: str,
    adb_serial: str,
    trial_logger: object,
) -> callable:
    from android_world.env import android_world_controller

    original_apply = android_world_controller.apply_a11y_forwarder_app_wrapper
    package_name = "com.google.androidenv.accessibilityforwarder"

    def patched_apply(env: object, install_a11y_forwarding_app: bool) -> object:
        should_install = bool(install_a11y_forwarding_app)
        if should_install and _android_package_installed(
            adb_path=adb_path,
            adb_serial=adb_serial,
            package_name=package_name,
        ):
            trial_logger.info(
                "AndroidWorld accessibility forwarder already exists on %s; skipping APK re-download.",
                adb_serial,
            )
            should_install = False
        wrapped = original_apply(env, should_install)
        _ensure_androidworld_accessibility_runtime(
            adb_path=adb_path,
            adb_serial=adb_serial,
            trial_logger=trial_logger,
        )
        return wrapped

    android_world_controller.apply_a11y_forwarder_app_wrapper = patched_apply

    def restore() -> None:
        android_world_controller.apply_a11y_forwarder_app_wrapper = original_apply

    return restore


def _extract_androidworld_shell_date_output(raw_output: str) -> str:
    stripped = raw_output.strip()
    if not stripped:
        return stripped
    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    matches = [line for line in lines if _ANDROIDWORLD_SHELL_DATE_PATTERN.fullmatch(line)]
    if matches:
        return matches[-1]
    match = _ANDROIDWORLD_SHELL_DATE_PATTERN.search(stripped)
    if match is not None:
        return match.group(0).strip()
    return stripped


def _extract_androidworld_unix_timestamp_output(raw_output: str) -> str:
    stripped = raw_output.strip()
    if not stripped:
        return stripped
    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    numeric_lines = [line for line in lines if line.isdigit()]
    if numeric_lines:
        return numeric_lines[-1]
    match = _ANDROIDWORLD_UNIX_TIMESTAMP_PATTERN.search(stripped)
    if match is not None:
        return match.group(0).strip()
    return stripped


def _patch_androidworld_datetime_utils(*, trial_logger: object) -> callable:
    try:
        from android_world.utils import datetime_utils as androidworld_datetime_utils
    except ModuleNotFoundError:
        return lambda: None

    original_advance_system_time = androidworld_datetime_utils.advance_system_time

    def patched_advance_system_time(delta: datetime.timedelta, env: object) -> None:
        response = androidworld_datetime_utils.adb_utils.issue_generic_request(["shell", "date"], env)
        raw_output = response.generic.output.decode(errors="replace")
        cleaned_output = _extract_androidworld_shell_date_output(raw_output)
        if cleaned_output != raw_output.strip():
            trial_logger.warning(
                "AndroidWorld shell date output included extra log lines; using sanitized timestamp '%s'.",
                cleaned_output,
            )
        current_time = datetime.datetime.strptime(cleaned_output, _ANDROIDWORLD_SHELL_DATE_FORMAT)
        androidworld_datetime_utils.adb_utils.issue_generic_request(
            ["shell", "date", (current_time + delta).strftime("%m%d%H%M%y.%S")],
            env,
        )

    androidworld_datetime_utils.advance_system_time = patched_advance_system_time

    def restore() -> None:
        androidworld_datetime_utils.advance_system_time = original_advance_system_time

    return restore


def _patch_androidworld_sms_validator_time(*, trial_logger: object) -> callable:
    try:
        from android_world.task_evals.common_validators import sms_validators
    except ModuleNotFoundError:
        return lambda: None

    if not hasattr(sms_validators, "SimpleSMSSendSms"):
        return lambda: None
    original_get_android_time = sms_validators.SimpleSMSSendSms.get_android_time

    def patched_get_android_time(self: object, env: object) -> int:
        adb_output = sms_validators.adb_utils.issue_generic_request(
            ["shell", "date", "+%s"],
            env,
        )
        raw_value = getattr(getattr(adb_output, "generic", None), "output", b"")
        if isinstance(raw_value, bytes):
            raw_output = raw_value.decode(errors="replace")
        else:
            raw_output = str(raw_value)
        cleaned_output = _extract_androidworld_unix_timestamp_output(raw_output)
        if cleaned_output != raw_output.strip():
            trial_logger.warning(
                "AndroidWorld shell date +%%s output included extra log lines; using sanitized timestamp '%s'.",
                cleaned_output,
            )
        return int(cleaned_output) * 1000

    sms_validators.SimpleSMSSendSms.get_android_time = patched_get_android_time

    def restore() -> None:
        sms_validators.SimpleSMSSendSms.get_android_time = original_get_android_time

    return restore


def _is_information_retrieval_task(task: object) -> bool:
    try:
        from android_world.task_evals.information_retrieval import information_retrieval
    except Exception:
        return False
    return isinstance(task, information_retrieval.InformationRetrieval)


def _strip_wrapping_quotes(text: str) -> str:
    cleaned = text.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
        return cleaned[1:-1].strip()
    return cleaned


def _extract_information_retrieval_answer_text(raw_output: object) -> str:
    candidates = [
        _clean_action_text(getattr(raw_output, "action_text", None)),
        _clean_action_text(getattr(raw_output, "raw_content", None)),
        _clean_reasoning_text(getattr(raw_output, "thinking", None)),
    ]
    for candidate in candidates:
        if candidate is None:
            continue
        cleaned = _strip_wrapping_quotes(candidate)
        if not cleaned or cleaned.startswith("do(") or cleaned.startswith("finish("):
            continue
        return cleaned
    return ""


def _cache_information_retrieval_answer(
    *,
    env: object,
    task: object,
    action_record: ActionRecord | None,
    raw_output: object,
    trial_logger: object | None = None,
    step_index: int | None = None,
) -> str:
    if not _is_information_retrieval_task(task):
        return ""
    if action_record is not None:
        parsed_action = dict(action_record.parsed_action)
        if str(parsed_action.get("_metadata", "")).strip() == "finish":
            message = str(parsed_action.get("message", "")).strip()
            if message:
                setattr(env, "interaction_cache", message)
                if trial_logger is not None and step_index is not None:
                    trial_logger.info(
                        "Step %s captured AndroidWorld information-retrieval answer: %s",
                        step_index,
                        message,
                    )
                return message
    answer = _extract_information_retrieval_answer_text(raw_output)
    if answer:
        setattr(env, "interaction_cache", answer)
        if trial_logger is not None and step_index is not None:
            trial_logger.info(
                "Step %s captured AndroidWorld information-retrieval answer: %s",
                step_index,
                answer,
            )
    return answer


def _execute_agent_step(
    *,
    phone_agent: object,
    task_prompt: str | None,
    output_dir: Path,
    step_index: int,
) -> tuple[object, str, object]:
    last_response: dict[str, object] = {}
    original_request = phone_agent.model_client.request

    def traced_request(messages: list[dict[str, Any]]) -> object:
        response = _sanitize_model_response(original_request(messages))
        last_response["response"] = response
        return response

    phone_agent.model_client.request = traced_request
    raw_steps_dir = output_dir / "raw" / "open_autoglm_androidworld" / "steps"
    raw_steps_dir.mkdir(parents=True, exist_ok=True)
    console_path = raw_steps_dir / f"{step_index:04d}.console.txt"
    result = None
    try:
        result, captured_output = _run_with_console_capture(
            lambda: phone_agent.step(task_prompt) if task_prompt is not None else phone_agent.step(),
            file_paths=[output_dir / "trial.log", console_path],
        )
    finally:
        phone_agent.model_client.request = original_request
    response = last_response.get("response")
    if response is None:
        detail_parts: list[str] = []
        if getattr(result, "message", None):
            detail_parts.append(f"PhoneAgent message: {result.message}")
        if captured_output.strip():
            detail_parts.append(f"Captured output: {captured_output.strip()}")
        combined_detail = " | ".join(detail_parts)
        if _looks_like_model_endpoint_failure(combined_detail):
            raise _build_model_endpoint_error(combined_detail)
        detail = f" {' | '.join(detail_parts)}" if detail_parts else ""
        raise RuntimeError(
            "AUTOGLM_BRIDGE_ERROR: Open-AutoGLM did not return a structured model response for the current step."
            f"{detail}"
        )
    return result, captured_output, response


def _run_pair(request: dict[str, object]) -> dict[str, object]:
    trial_dir = Path(str(request["output_dir"]))
    raw_dir = trial_dir / "raw" / "open_autoglm_androidworld"
    raw_dir.mkdir(parents=True, exist_ok=True)
    trial_id = str(request.get("trial_id", "") or "open_autoglm__androidworld")
    trial_logger = get_trial_logger(trial_id, trial_dir / "trial.log")

    repo_paths = request.get("repo_paths", {})
    if not isinstance(repo_paths, dict):
        raise RuntimeError("AUTOGLM_BRIDGE_ERROR: repo_paths must be a JSON object.")
    open_autoglm_repo = Path(str(repo_paths.get("open_autoglm", "")))
    androidworld_repo = Path(str(repo_paths.get("androidworld", "")))
    for repo_path in (open_autoglm_repo, androidworld_repo):
        if repo_path.as_posix() and repo_path.as_posix() not in sys.path:
            sys.path.insert(0, repo_path.as_posix())

    _require_runtime_import(
        "phone_agent.agent",
        install_hint="python -m pip install -r references/agents/Open-AutoGLM/requirements.txt",
    )
    _require_runtime_import(
        "android_world.env.env_launcher",
        install_hint="python -m pip install -r references/benchmarks/android_world/requirements.txt",
    )

    model_payload = request.get("model", {})
    if not isinstance(model_payload, dict):
        raise RuntimeError("MODEL_CONFIG_ERROR: model payload must be an object.")
    model_id = str(model_payload.get("model_id", "") or "").strip()
    if not model_id:
        raise RuntimeError("MODEL_CONFIG_ERROR: model_id is empty.")
    if not os.environ.get("PHONE_AGENT_BASE_URL", "").strip():
        raise RuntimeError("MODEL_CONFIG_ERROR: PHONE_AGENT_BASE_URL is not set.")
    if not os.environ.get("PHONE_AGENT_API_KEY", "").strip():
        raise RuntimeError("MODEL_CONFIG_ERROR: PHONE_AGENT_API_KEY is not set.")

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
    from phone_agent import PhoneAgent
    from phone_agent.agent import AgentConfig
    from phone_agent.device_factory import DeviceType, set_device_type
    from phone_agent.model import ModelConfig
    from snowl_mobile.adapters.agents.open_autoglm import OpenAutoGLMAgentAdapter, OpenAutoGLMRawOutput

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
            "A fresh emulator can be prepared either by letting the direct pair run perform task-scoped app setup "
            "or by running the benchmark setup flow as an optional preflight. "
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
            with contextlib.suppress(Exception):
                current_env.close()
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
    task_instruction = str(
        request.get("task_instruction")
        or task_payload.get("instruction")
        or ""
    ).strip()
    task = None
    trajectory_steps: list[dict[str, object]] = []
    raw_artifacts: dict[str, str] = {}
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
        "control_backend": "adb",
        "pair_bridge": "open_autoglm__androidworld",
        "python_executable": sys.executable,
        "worker_env_name": str(benchmark_options.get("worker_env_name", "") or ""),
    }

    raw_steps_dir = raw_dir / "steps"
    raw_steps_dir.mkdir(parents=True, exist_ok=True)
    task_metadata_path = raw_dir / "task.json"
    agent_finished = False

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
        composed_task_prompt = _compose_task_prompt(
            task_instruction=task_instruction,
            task_name=task_name,
        )
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
                "AndroidWorld task-scoped app setup completed inside the Open-AutoGLM pair bridge runtime."
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
        initial_observation, initial_artifacts = _persist_observation(
            state=initial_state,
            env=env,
            raw_dir=raw_dir / "bootstrap",
            trial_dir=trial_dir,
        )
        raw_artifacts.update({f"androidworld_{key}": value for key, value in initial_artifacts.items()})
        platform_metrics["goal"] = str(getattr(task, "goal", "") or "")
        platform_metrics["task_complexity"] = float(getattr(task, "complexity", 0.0) or 0.0)
        platform_metrics["task_instance_seed"] = task_instance_seed
        platform_metrics["bootstrap_observation_path"] = initial_observation["screenshot_path"]
        trial_logger.info(
            "Environment initialization completed. Bootstrap observation saved to %s",
            initial_observation["screenshot_path"],
        )
        notes.append("AndroidWorld task bootstrap completed inside the pair-specific Open-AutoGLM bridge runtime.")

        set_device_type(DeviceType.ADB)
        model_config = ModelConfig(
            base_url=os.environ["PHONE_AGENT_BASE_URL"],
            api_key=os.environ["PHONE_AGENT_API_KEY"],
            model_name=model_id,
        )
        agent_config = AgentConfig(
            max_steps=int(request.get("max_steps", 20) or 20),
            device_id=adb_serial,
            lang="en",
            verbose=True,
        )
        phone_agent = PhoneAgent(model_config=model_config, agent_config=agent_config)
        restore_coordinate_patch = _patch_action_coordinate_conversion(phone_agent)
        restore_launch_patch = _patch_launch_aliases(phone_agent)
        restore_type_patch, text_input_backend = _patch_type_input_fallback(
            phone_agent,
            adb_serial=adb_serial,
            adb_path=adb_path,
        )
        platform_metrics["text_input_backend"] = text_input_backend
        trial_logger.info("Text input backend selected: %s", text_input_backend)
        try:
            agent_adapter = OpenAutoGLMAgentAdapter()
            max_steps = int(request.get("max_steps", 20) or 20)
            for step_index in range(1, max_steps + 1):
                trial_logger.info("Step %s started", step_index)
                step_result, captured_output, response = _execute_agent_step(
                    phone_agent=phone_agent,
                    task_prompt=composed_task_prompt if step_index == 1 else None,
                    output_dir=trial_dir,
                    step_index=step_index,
                )
                response_text_path = raw_steps_dir / f"{step_index:04d}.model_response.txt"
                response_json_path = raw_steps_dir / f"{step_index:04d}.model_response.json"
                response_text_path.write_text(str(getattr(response, "raw_content", "") or "") + "\n", encoding="utf-8")
                response_json_path.write_text(
                    json.dumps(
                        {
                            "thinking": str(getattr(response, "thinking", "") or ""),
                            "action": str(getattr(response, "action", "") or ""),
                            "raw_content": str(getattr(response, "raw_content", "") or ""),
                            "time_to_first_token": _safe_value(getattr(response, "time_to_first_token", None)),
                            "time_to_thinking_end": _safe_value(getattr(response, "time_to_thinking_end", None)),
                            "total_time": _safe_value(getattr(response, "total_time", None)),
                            "captured_console": captured_output,
                            "finished": bool(getattr(step_result, "finished", False)),
                            "success": bool(getattr(step_result, "success", False)),
                            "message": str(getattr(step_result, "message", "") or ""),
                        },
                        indent=2,
                        sort_keys=True,
                    ),
                    encoding="utf-8",
                )
                raw_output = OpenAutoGLMRawOutput(
                    thinking=str(getattr(response, "thinking", "") or ""),
                    action_text=str(getattr(response, "action", "") or ""),
                    raw_content=str(getattr(response, "raw_content", "") or ""),
                    time_to_first_token_ms=int(round(float(getattr(response, "time_to_first_token", 0.0) or 0.0) * 1000)),
                    time_to_thinking_end_ms=int(round(float(getattr(response, "time_to_thinking_end", 0.0) or 0.0) * 1000)),
                    total_time_ms=int(round(float(getattr(response, "total_time", 0.0) or 0.0) * 1000)),
                )
                information_retrieval_answer = ""
                try:
                    action_record = agent_adapter.normalize_action(raw_output)
                except IntegrationError:
                    information_retrieval_answer = _cache_information_retrieval_answer(
                        env=env_ref["env"],
                        task=task,
                        action_record=None,
                        raw_output=raw_output,
                        trial_logger=trial_logger,
                        step_index=step_index,
                    )
                    if not information_retrieval_answer:
                        raise
                    platform_metrics["information_retrieval_answer"] = information_retrieval_answer
                    action_record = ActionRecord(
                        agent_raw_output=raw_output.raw_content,
                        parsed_action={"_metadata": "finish", "message": information_retrieval_answer},
                        executed_action={
                            "schema": "autoglm_phone_action_v1",
                            "kind": "finish",
                            "action_name": "finish",
                            "normalized_action": "finish",
                            "arguments": {"message": information_retrieval_answer},
                            "coordinate_space": "",
                            "coordinate_fields": [],
                            "requires_confirmation": False,
                            "requires_human_takeover": False,
                        },
                        execution_result={
                            "thinking": raw_output.thinking,
                            "time_to_first_token_ms": raw_output.time_to_first_token_ms,
                            "time_to_thinking_end_ms": raw_output.time_to_thinking_end_ms,
                            "total_time_ms": raw_output.total_time_ms,
                        },
                    )
                else:
                    information_retrieval_answer = _cache_information_retrieval_answer(
                        env=env_ref["env"],
                        task=task,
                        action_record=action_record,
                        raw_output=raw_output,
                        trial_logger=trial_logger,
                        step_index=step_index,
                    )
                    if information_retrieval_answer:
                        platform_metrics["information_retrieval_answer"] = information_retrieval_answer
                trial_logger.info(
                    "Step %s action selected: %s",
                    step_index,
                    str(getattr(response, "action", "") or "").strip() or "<empty action>",
                )

                step_state = _run_androidworld_env_operation(
                    env_ref=env_ref,
                    trial_logger=trial_logger,
                    description=f"step {step_index} observation capture for '{task_name}'",
                    operation=lambda: env_ref["env"].get_state(wait_to_stabilize=True),
                    reload_env=_reload_env,
                )
                env = env_ref["env"]
                step_observation, step_artifacts = _persist_observation(
                    state=step_state,
                    env=env,
                    raw_dir=raw_steps_dir / f"{step_index:04d}",
                    trial_dir=trial_dir,
                )
                step_observation, platform_step_artifacts = _persist_platform_step_artifacts(
                    step_index=step_index,
                    state=step_state,
                    env=env,
                    trial_dir=trial_dir,
                    observation=step_observation,
                )
                raw_artifacts.update(
                    {f"step_{step_index:04d}_{key}": value for key, value in step_artifacts.items()}
                )
                raw_artifacts.update(platform_step_artifacts)
                trial_logger.info(
                    "Step %s observation captured: package=%s activity=%s",
                    step_index,
                    step_observation.get("package_name"),
                    step_observation.get("activity"),
                )
                trial_logger.info(
                    "Step %s observation preview: %s",
                    step_index,
                    _format_observation_preview(step_observation),
                )
                console_path = raw_steps_dir / f"{step_index:04d}.console.txt"
                trajectory_steps.append(
                    _step_payload(
                        step_index=step_index,
                        observation=step_observation,
                        action_record=action_record,
                        task_instruction=task_instruction,
                        thinking=str(getattr(response, "thinking", "") or ""),
                        action_text=str(getattr(response, "action", "") or ""),
                        response_text_path=response_text_path,
                        response_json_path=response_json_path,
                        console_path=console_path,
                        persisted_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        trial_dir=trial_dir,
                    )
                )
                if getattr(step_result, "finished", False) or information_retrieval_answer:
                    agent_finished = True
                    if information_retrieval_answer and not getattr(step_result, "finished", False):
                        trial_logger.info(
                            "Step %s finished after caching the AndroidWorld information-retrieval answer.",
                            step_index,
                        )
                        notes.append(
                            f"Open-AutoGLM answered the AndroidWorld information-retrieval task after {step_index} step(s)."
                        )
                    else:
                        trial_logger.info("Step %s requested finish()", step_index)
                        notes.append(f"Open-AutoGLM finished after {step_index} step(s).")
                    break
            else:
                trial_logger.info(
                    "Open-AutoGLM reached max_steps=%s without emitting finish().",
                    max_steps,
                )
                notes.append("Open-AutoGLM reached the configured max_steps without emitting finish().")
        finally:
            restore_type_patch()
            restore_launch_patch()
            restore_coordinate_patch()

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
        platform_metrics["final_observation_path"] = final_observation["screenshot_path"]
        platform_metrics["steps_executed"] = len(trajectory_steps)
        platform_metrics["finished"] = agent_finished
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
        notes.append("AndroidWorld native scoring completed after the Open-AutoGLM step loop.")
    except RuntimeError:
        raise
    except Exception as error:
        if _looks_like_model_endpoint_failure(f"{type(error).__name__}: {error}"):
            raise _build_model_endpoint_error(f"{type(error).__name__}: {error}") from error
        raise RuntimeError(
            f"AUTOGLM_BRIDGE_ERROR: unexpected bridge runtime failure: {error}"
        ) from error
    finally:
        current_env = env_ref.get("env", env)
        if task is not None and bool(getattr(task, "initialized", False)):
            try:
                task.tear_down(current_env)
            except Exception:
                notes.append("AndroidWorld task tear_down raised; continuing after capturing artifacts.")
        with contextlib.suppress(Exception):
            current_env.close()
        restore_sqlite_patch()
        restore_sms_time_patch()
        restore_datetime_patch()
        restore_a11y_patch()
        restore_clear_directory_patch()

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


def main(argv: list[str]) -> int:
    os.environ.setdefault("GRPC_VERBOSITY", "ERROR")
    os.environ.setdefault("GRPC_TRACE", "")

    if len(argv) != 3:
        print(
            "usage: python -m snowl_mobile.adapters.bridges.open_autoglm_androidworld_runtime "
            "<request-json> <result-json>",
            file=sys.stderr,
        )
        return 2

    request_path = Path(argv[1]).resolve()
    result_path = Path(argv[2]).resolve()
    request = _load_json(request_path)
    output_dir = Path(str(request.get("output_dir", result_path.parent)))
    raw_dir = output_dir / "raw" / "open_autoglm_androidworld"
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
