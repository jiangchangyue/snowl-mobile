from __future__ import annotations

import copy
import importlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
import types
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_BENCHMARK_APP_ALIASES = {
    "photonote": ("com.chartreux.photo_note",),
    "photo_note": ("com.chartreux.photo_note",),
    "photo note": ("com.chartreux.photo_note",),
    "bank": ("com.example.bankApp",),
    "bankapp": ("com.example.bankApp",),
    "stock": ("com.alifesoftware.stocktrainer",),
    "stocktrainer": ("com.alifesoftware.stocktrainer",),
    "stock trainer": ("com.alifesoftware.stocktrainer",),
    "messages": (
        "com.simplemobiletools.smsmessenger",
        "com.google.android.apps.messaging",
        "com.android.messaging",
    ),
    "sms": (
        "com.simplemobiletools.smsmessenger",
        "com.google.android.apps.messaging",
        "com.android.messaging",
    ),
    "chrome": ("com.android.chrome",),
    "browser": ("com.android.chrome",),
    "maps": ("com.google.android.apps.maps",),
    "googlemaps": ("com.google.android.apps.maps",),
    "joplin": ("net.cozic.joplin",),
    "memo": ("net.cozic.joplin",),
    "notes": ("net.cozic.joplin",),
    "youtube": ("com.google.android.youtube",),
    "settings": ("com.android.settings",),
}


def _utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _fallback_smart_resize(
    height: int,
    width: int,
    factor: int = 16,
    min_pixels: int | None = None,
    max_pixels: int | None = None,
) -> tuple[int, int]:
    image_min_token_num = 4
    image_max_token_num = 16384
    max_ratio = 200

    max_pixels = max_pixels if max_pixels is not None else (image_max_token_num * factor**2)
    min_pixels = min_pixels if min_pixels is not None else (image_min_token_num * factor**2)
    if max_pixels < min_pixels:
        raise ValueError("max_pixels must be >= min_pixels.")
    if max(height, width) / min(height, width) > max_ratio:
        raise ValueError(
            f"Aspect ratio must be < {max_ratio}, got {max(height, width) / min(height, width)}"
        )

    def _round(value: float) -> int:
        return round(value / factor) * factor

    def _floor(value: float) -> int:
        return math.floor(value / factor) * factor

    def _ceil(value: float) -> int:
        return math.ceil(value / factor) * factor

    height_bar = max(factor, _round(height))
    width_bar = max(factor, _round(width))

    if height_bar * width_bar > max_pixels:
        beta = math.sqrt((height * width) / max_pixels)
        height_bar = _floor(height / beta)
        width_bar = _floor(width / beta)
    elif height_bar * width_bar < min_pixels:
        beta = math.sqrt(min_pixels / (height * width))
        height_bar = _ceil(height * beta)
        width_bar = _ceil(width * beta)

    return height_bar, width_bar


def _install_qwen_vl_utils_shim_if_needed() -> None:
    if "qwen_vl_utils" in sys.modules:
        return
    try:
        importlib.import_module("qwen_vl_utils")
        return
    except ModuleNotFoundError:
        shim = types.ModuleType("qwen_vl_utils")
        shim.smart_resize = _fallback_smart_resize
        sys.modules["qwen_vl_utils"] = shim
        return


def _normalize_mobile_use_image_path(image_path: str) -> str:
    text = str(image_path).strip()
    if text.startswith("file://"):
        return text[len("file://") :]
    return text


def _install_mobile_use_path_shims(utils_module: object) -> None:
    original_image_to_base64 = getattr(utils_module, "image_to_base64")

    def _shimmed_image_to_base64(image_path: str) -> str:
        return original_image_to_base64(_normalize_mobile_use_image_path(image_path))

    setattr(utils_module, "image_to_base64", _shimmed_image_to_base64)


def _extract_json_object_from_model_output(text: str) -> dict[str, Any] | None:
    def _next_nonspace_char(candidate: str, start_index: int) -> str:
        for index in range(start_index, len(candidate)):
            if not candidate[index].isspace():
                return candidate[index]
        return ""

    def _load_candidate(candidate: str) -> tuple[dict[str, Any] | None, str]:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as error:
            if (
                error.msg == "Expecting ',' delimiter"
                and 0 <= error.pos < len(candidate)
                and candidate[error.pos] == '"'
                and _next_nonspace_char(candidate, error.pos + 1) in {",", "}", "]"}
            ):
                repaired_candidate = candidate[: error.pos] + candidate[error.pos + 1 :]
                try:
                    repaired = json.loads(repaired_candidate)
                except json.JSONDecodeError:
                    return None, ""
                if isinstance(repaired, dict):
                    return repaired, "fallback_json_repair"
            return None, ""
        if isinstance(parsed, dict):
            return parsed, "fallback_json_extraction"
        return None, ""

    candidates = [text.strip()]
    candidates.extend(
        re.findall(
            r"<tool_call>\s*(\{.*?\})\s*</tool_call>",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )
    )
    candidates.extend(
        re.findall(
            r"⚗\s*(\{.*?\})\s*⚗",
            text,
            flags=re.DOTALL,
        )
    )
    candidates.extend(re.findall(r"({.*})", text, flags=re.DOTALL))
    for candidate in candidates:
        if not candidate:
            continue
        parsed, parse_mode = _load_candidate(candidate)
        if isinstance(parsed, dict):
            parsed["_fallback_parse_mode"] = parse_mode
            return parsed
    return None


def _parse_action_with_fallback(
    output_text: str,
    *,
    parse_action_func: object,
) -> tuple[dict[str, Any], str]:
    try:
        parsed = parse_action_func(output_text)
    except Exception as exc:
        fallback_payload = _extract_json_object_from_model_output(output_text)
        if isinstance(fallback_payload, dict) and isinstance(
            fallback_payload.get("arguments"), dict
        ):
            parse_mode = str(fallback_payload.pop("_fallback_parse_mode", "")).strip()
            return fallback_payload, parse_mode or "fallback_json_extraction"
        raise exc
    if not isinstance(parsed, dict):
        raise RuntimeError(
            f"Mobile-Agent-v3.5 parse_action returned {type(parsed).__name__}, expected dict."
        )
    return parsed, "upstream_parse_action"


def _truncate_parse_error_message(message: str, *, limit: int = 240) -> str:
    normalized = " ".join(str(message).split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _build_parse_error_termination_action(parse_error: Exception) -> tuple[dict[str, Any], str]:
    parse_error_message = _truncate_parse_error_message(
        str(parse_error).strip() or type(parse_error).__name__
    )
    return (
        {
            "_metadata": "synthetic_parse_error",
            "name": "mobile_use",
            "arguments": {
                "action": "terminate",
                "status": "failure",
                "text": f"action_parse_error: {parse_error_message}",
            },
        },
        parse_error_message,
    )


def _coordinate_pairs(arguments: dict[str, Any]) -> list[tuple[str, float, float]]:
    pairs: list[tuple[str, float, float]] = []
    for key in ("coordinate", "coordinate1", "coordinate2"):
        value = arguments.get(key)
        if (
            isinstance(value, (list, tuple))
            and len(value) >= 2
            and all(isinstance(item, (int, float)) for item in value[:2])
        ):
            pairs.append((key, float(value[0]), float(value[1])))
    return pairs


def _infer_coordinate_space(
    arguments: dict[str, Any],
    *,
    screen_width: int,
    screen_height: int,
) -> str:
    pairs = _coordinate_pairs(arguments)
    if not pairs:
        return ""
    for _key, x, y in pairs:
        if x > 1000 or y > 1000:
            return "absolute_pixels"
    for _key, x, y in pairs:
        if x > screen_width or y > screen_height:
            return "relative_0_1000"
    return ""


def _clamp_coordinate_arguments(
    arguments: dict[str, Any],
    *,
    screen_width: int,
    screen_height: int,
) -> dict[str, Any]:
    clamped = copy.deepcopy(arguments)
    max_x = max(screen_width - 1, 0)
    max_y = max(screen_height - 1, 0)
    for key, x, y in _coordinate_pairs(clamped):
        clamped[key][0] = max(0, min(int(x), max_x))
        clamped[key][1] = max(0, min(int(y), max_y))
    return clamped


def _materialize_executed_arguments(
    raw_arguments: dict[str, Any],
    *,
    image_width: int,
    image_height: int,
    rescale_coordinates: object,
    resized_width: int,
    resized_height: int,
    preferred_coordinate_space: str = "",
) -> tuple[dict[str, Any], str]:
    executed_arguments = copy.deepcopy(raw_arguments)
    if not _coordinate_pairs(executed_arguments):
        return executed_arguments, ""
    coordinate_space = _infer_coordinate_space(
        executed_arguments,
        screen_width=image_width,
        screen_height=image_height,
    )
    if not coordinate_space:
        coordinate_space = preferred_coordinate_space or "absolute_pixels"
    if coordinate_space == "absolute_pixels":
        return (
            _clamp_coordinate_arguments(
                executed_arguments,
                screen_width=image_width,
                screen_height=image_height,
            ),
            "absolute_pixels",
        )
    return (
        rescale_coordinates(executed_arguments, resized_width, resized_height),
        "relative_0_1000",
    )


def _post_action_settle_seconds(action_type: str) -> float:
    normalized = action_type.strip().lower()
    if normalized == "type":
        return 1.8
    if normalized in {"click", "long_press", "swipe", "scroll", "open", "system_button", "key"}:
        return 0.9
    if normalized == "wait":
        return 0.2
    return 0.0


def _remove_file_if_present(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        return


def _validate_captured_image(image_path: Path) -> None:
    pil_image_module = importlib.import_module("PIL.Image")
    image = pil_image_module.open(str(image_path))
    try:
        verify = getattr(image, "verify", None)
        if callable(verify):
            verify()
            return
        size = getattr(image, "size", None)
        if not size:
            width = getattr(image, "width", None)
            height = getattr(image, "height", None)
            if width and height:
                size = (width, height)
        if not (isinstance(size, tuple) and len(size) == 2):
            raise RuntimeError(
                f"Captured screenshot '{image_path}' did not expose a readable image size."
            )
    finally:
        close = getattr(image, "close", None)
        if callable(close):
            close()


def _capture_validated_screenshot(
    *,
    adb_tools: object,
    adb_serial: str,
    screenshot_path: Path,
    max_attempts: int = 3,
    retry_delay_seconds: float = 0.2,
) -> None:
    last_error: Exception | None = None
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, max_attempts + 1):
        _remove_file_if_present(screenshot_path)
        try:
            if not adb_tools.get_screenshot(str(screenshot_path)):
                raise RuntimeError(
                    f"Mobile-Agent-v3.5 screenshot capture failed for device '{adb_serial}'."
                )
            _validate_captured_image(screenshot_path)
            return
        except Exception as exc:
            last_error = exc
            _remove_file_if_present(screenshot_path)
            if attempt < max_attempts:
                time.sleep(retry_delay_seconds)
    raise RuntimeError(
        "Mobile-Agent-v3.5 screenshot capture produced an unreadable image "
        f"for device '{adb_serial}' after {max_attempts} attempt(s)."
    ) from last_error


def _capture_observation(
    *,
    adb_tools: object,
    adb_path: str,
    adb_serial: str,
    screenshot_path: Path,
    xml_path: Path,
    capture_xml_via_adb: bool,
) -> None:
    _capture_validated_screenshot(
        adb_tools=adb_tools,
        adb_serial=adb_serial,
        screenshot_path=screenshot_path,
    )
    if not capture_xml_via_adb:
        xml_path.parent.mkdir(parents=True, exist_ok=True)
        xml_path.write_text("<hierarchy></hierarchy>\n", encoding="utf-8")
        return
    _dump_ui_hierarchy_xml(adb_path=adb_path, adb_serial=adb_serial, xml_path=xml_path)


def _extract_bounds_center(bounds_text: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds_text.strip())
    if match is None:
        return None
    left, top, right, bottom = (int(item) for item in match.groups())
    if right <= left or bottom <= top:
        return None
    return ((left + right) // 2, (top + bottom) // 2)


def _find_editable_field_center(xml_path: Path) -> tuple[int, int] | None:
    if not xml_path.exists():
        return None
    try:
        root = ET.fromstring(xml_path.read_text(encoding="utf-8"))
    except (ET.ParseError, OSError):
        return None

    best_center: tuple[int, int] | None = None
    best_score = -1
    best_y = -1
    for node in root.iter():
        attributes = node.attrib
        bounds = _extract_bounds_center(str(attributes.get("bounds", "")))
        if bounds is None:
            continue
        class_name = str(attributes.get("class", "")).lower()
        resource_id = str(attributes.get("resource-id", "")).lower()
        text = str(attributes.get("text", "")).lower()
        content_desc = str(attributes.get("content-desc", "")).lower()
        score = 0
        if "edittext" in class_name:
            score += 5
        if attributes.get("focused") == "true":
            score += 4
        if attributes.get("focusable") == "true":
            score += 2
        if any(
            token in f"{resource_id} {text} {content_desc}"
            for token in ("message", "compose", "input", "sms", "chat")
        ):
            score += 2
        if score > best_score or (score == best_score and bounds[1] > best_y):
            best_score = score
            best_center = bounds
            best_y = bounds[1]
    return best_center if best_score > 0 else None


def _focus_editable_field_if_present(
    *,
    adb_tools: object,
    xml_path: Path | None,
) -> str:
    if xml_path is None:
        return ""
    center = _find_editable_field_center(xml_path)
    if center is None:
        return ""
    adb_tools.click(int(center[0]), int(center[1]))
    time.sleep(0.35)
    return f"Focused editable field at {center[0]},{center[1]} before typing."


def _type_text_via_adb_keyboard(
    *,
    adb_path: str,
    adb_serial: str,
    text: str,
) -> tuple[bool, str]:
    ime_id = "com.android.adbkeyboard/.AdbIME"
    enable_result = _run_adb(
        adb_path=adb_path,
        adb_serial=adb_serial,
        argv=["shell", "ime", "enable", ime_id],
    )
    set_result = _run_adb(
        adb_path=adb_path,
        adb_serial=adb_serial,
        argv=["shell", "ime", "set", ime_id],
    )
    time.sleep(0.1)
    broadcast_result = _run_adb(
        adb_path=adb_path,
        adb_serial=adb_serial,
        argv=["shell", "am", "broadcast", "-a", "ADB_INPUT_TEXT", "--es", "msg", text],
        timeout_sec=30,
    )
    time.sleep(0.1)
    disable_result = _run_adb(
        adb_path=adb_path,
        adb_serial=adb_serial,
        argv=["shell", "ime", "disable", ime_id],
    )
    if (
        enable_result.returncode == 0
        and set_result.returncode == 0
        and broadcast_result.returncode == 0
    ):
        return True, "Typed text via ADB Keyboard broadcast."
    details = {
        "enable_returncode": enable_result.returncode,
        "set_returncode": set_result.returncode,
        "broadcast_returncode": broadcast_result.returncode,
        "disable_returncode": disable_result.returncode,
        "broadcast_stdout": broadcast_result.stdout.strip(),
        "broadcast_stderr": broadcast_result.stderr.strip(),
    }
    return False, f"ADB Keyboard path failed: {json.dumps(details, ensure_ascii=False, sort_keys=True)}"


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
        timeout_sec=30,
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


def _xml_contains_expected_text(xml_path: Path, expected: str) -> bool:
    if not expected.strip() or not xml_path.exists():
        return False
    try:
        xml_content = xml_path.read_text(encoding="utf-8").lower()
    except OSError:
        return False
    normalized_expected = " ".join(expected.lower().split())
    return normalized_expected in " ".join(xml_content.split())


def _history_tool_call_block(parsed_action: dict[str, Any]) -> str:
    payload = {
        "name": str(parsed_action.get("name", "mobile_use")),
        "arguments": dict(parsed_action.get("arguments", {})),
    }
    return "<tool_call>\n" + json.dumps(payload, ensure_ascii=True) + "\n</tool_call>"


def _history_action_summary(
    *,
    raw_output: str,
    parsed_action: dict[str, Any],
    action_status: dict[str, object],
    task_category: str,
    risk_level: str,
) -> str:
    reasoning_text = _extract_reasoning_text(raw_output)
    if reasoning_text:
        return f"Action: {reasoning_text}"
    action_type = str(dict(parsed_action.get("arguments", {})).get("action", "")).strip()
    if action_type:
        return f"Action: Execute {action_type}."
    return "Action: Continue the task."


def _history_output_text(
    *,
    raw_output: str,
    parsed_action: dict[str, Any],
    action_status: dict[str, object],
    task_category: str,
    risk_level: str,
) -> str:
    return (
        _history_action_summary(
            raw_output=raw_output,
            parsed_action=parsed_action,
            action_status=action_status,
            task_category=task_category,
            risk_level=risk_level,
        )
        + "\n"
        + _history_tool_call_block(parsed_action)
    )


def _probe_foreground_app(adb_path: str, adb_serial: str) -> tuple[str, str]:
    candidates = [
        ["shell", "dumpsys", "window", "windows"],
        ["shell", "dumpsys", "activity", "activities"],
    ]
    for argv in candidates:
        result = _run_adb(
            adb_path=adb_path,
            adb_serial=adb_serial,
            argv=argv,
            timeout_sec=15,
        )
        if result.returncode != 0:
            continue
        text = result.stdout
        for line in text.splitlines():
            if "mCurrentFocus" in line or "mFocusedApp" in line or "mResumedActivity" in line:
                if "/" in line:
                    tail = line.rsplit(" ", 1)[-1].strip().rstrip("}")
                    if "/" in tail:
                        package_name, activity = tail.split("/", 1)
                        return package_name.strip(), activity.strip()
    return "", ""


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected JSON object at {path}, got {type(payload).__name__}.")
    return payload


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _append_trial_log(trial_output_dir: Path, message: str, *, level: str = "INFO") -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
    trial_id = trial_output_dir.name
    line = f"[{timestamp}] [{level}] snowl_mobile.trial.{trial_id} - {message}\n"
    (trial_output_dir / "trial.log").open("a", encoding="utf-8").write(line)


def _render_action_summary(arguments: dict[str, Any]) -> str:
    action_name = str(arguments.get("action", "")).strip()
    payload = {key: value for key, value in arguments.items() if key != "action"}
    if payload:
        return f"{action_name} {json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
    return action_name


def _stream_platform_step_artifacts(
    *,
    trial_output_dir: Path,
    step_index: int,
    screenshot_path: Path,
    xml_path: Path,
) -> None:
    platform_steps_dir = trial_output_dir / "steps"
    platform_steps_dir.mkdir(parents=True, exist_ok=True)
    if screenshot_path.exists():
        shutil.copy2(
            screenshot_path,
            platform_steps_dir / f"{step_index:04d}.png",
        )
    if xml_path.exists():
        shutil.copy2(
            xml_path,
            platform_steps_dir / f"{step_index:04d}.xml",
        )


def _normalize_app_name(text: str) -> str:
    return text.lower().strip().replace(" ", "").replace("-", "").replace("_", "")


def _extract_reasoning_text(raw_output: str) -> str:
    if "<tool_call>" not in raw_output:
        return raw_output.strip()
    prefix = raw_output.split("<tool_call>", 1)[0]
    prefix = prefix.replace("Action:", "").strip()
    return prefix


def _adb_prefix(adb_path: str, adb_serial: str) -> list[str]:
    command = [adb_path]
    if adb_serial:
        command.extend(["-s", adb_serial])
    return command


def _run_adb(
    *,
    adb_path: str,
    adb_serial: str,
    argv: list[str],
    timeout_sec: int = 20,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*_adb_prefix(adb_path, adb_serial), *argv],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_sec,
    )


def _dump_ui_hierarchy_xml(
    *,
    adb_path: str,
    adb_serial: str,
    xml_path: Path,
) -> None:
    xml_path.parent.mkdir(parents=True, exist_ok=True)
    device_xml_path = "/sdcard/window_dump.xml"
    dump_result = _run_adb(
        adb_path=adb_path,
        adb_serial=adb_serial,
        argv=["shell", "uiautomator", "dump", device_xml_path],
    )
    if dump_result.returncode != 0:
        xml_path.write_text("<hierarchy></hierarchy>\n", encoding="utf-8")
        return
    pull_result = _run_adb(
        adb_path=adb_path,
        adb_serial=adb_serial,
        argv=["pull", device_xml_path, str(xml_path)],
    )
    _run_adb(
        adb_path=adb_path,
        adb_serial=adb_serial,
        argv=["shell", "rm", device_xml_path],
    )
    if pull_result.returncode != 0 or not xml_path.exists():
        xml_path.write_text("<hierarchy></hierarchy>\n", encoding="utf-8")


def _handle_open_action_noninteractive(
    *,
    adb_tools: object,
    instruction: str,
    app_name: str,
    name_package_dict: dict[str, list[str]],
    packages_name_dict: dict[str, list[str]],
    resolve_app_name_via_llm: object,
    resolver_api_key: str,
    resolver_base_url: str,
    resolver_model: str,
) -> dict[str, object]:
    installed_packages = adb_tools.get_package_name(all_packages=True)
    normalized = _normalize_app_name(app_name)
    candidate_packages = list(_BENCHMARK_APP_ALIASES.get(normalized, ()))
    candidate_packages.extend(name_package_dict.get(normalized, []))
    candidate_packages = list(dict.fromkeys(candidate_packages))
    for package_name in candidate_packages:
        if package_name in installed_packages:
            adb_tools.open_app(package_name)
            return {
                "ok": True,
                "message": f"Opened package '{package_name}' for app request '{app_name}'.",
                "opened_package": package_name,
            }

    installed_app_names: list[str] = []
    for package_name in installed_packages:
        app_names = packages_name_dict.get(package_name, [])
        if app_names:
            installed_app_names.append(app_names[0])
    installed_app_names = list(dict.fromkeys(installed_app_names))
    resolved_name = ""
    if resolver_api_key and resolver_base_url and installed_app_names:
        resolved_name = str(
            resolve_app_name_via_llm(
                instruction,
                ", ".join(installed_app_names),
                api_key=resolver_api_key,
                base_url=resolver_base_url,
                model=resolver_model,
            )
        ).strip()
    if resolved_name:
        resolved_normalized = _normalize_app_name(resolved_name)
        resolved_candidates = list(_BENCHMARK_APP_ALIASES.get(resolved_normalized, ()))
        resolved_candidates.extend(name_package_dict.get(resolved_normalized, []))
        resolved_candidates = list(dict.fromkeys(resolved_candidates))
        for package_name in resolved_candidates:
            if package_name in installed_packages:
                adb_tools.open_app(package_name)
                return {
                    "ok": True,
                    "message": (
                        f"Resolved app request '{app_name}' to '{resolved_name}' and opened package "
                        f"'{package_name}'."
                    ),
                    "opened_package": package_name,
                }

    return {
        "ok": False,
        "message": (
            f"Unable to resolve app '{app_name}' to an installed package without interactive input."
        ),
        "opened_package": "",
    }


def _execute_action(
    *,
    adb_tools: object,
    adb_path: str,
    adb_serial: str,
    instruction: str,
    raw_arguments: dict[str, Any],
    executed_arguments: dict[str, Any],
    current_xml_path: Path | None,
    name_package_dict: dict[str, list[str]],
    packages_name_dict: dict[str, list[str]],
    resolve_app_name_via_llm: object,
    resolver_api_key: str,
    resolver_base_url: str,
    resolver_model: str,
) -> dict[str, object]:
    action_type = str(raw_arguments.get("action", "")).strip()
    if action_type == "left_click":
        action_type = "click"
    status: dict[str, object] = {
        "ok": True,
        "action_type": action_type,
        "finished": False,
        "finish_flag": "",
        "message": "",
    }
    if action_type == "click":
        coordinate = executed_arguments.get("coordinate", [0, 0])
        adb_tools.click(int(coordinate[0]), int(coordinate[1]))
    elif action_type == "long_press":
        coordinate = executed_arguments.get("coordinate", [0, 0])
        duration_sec = float(raw_arguments.get("time", 0.8) or 0.8)
        adb_tools.long_press(int(coordinate[0]), int(coordinate[1]), int(duration_sec * 1000))
    elif action_type in {"swipe", "scroll"}:
        coordinate1 = executed_arguments.get("coordinate", [0, 0])
        coordinate2 = executed_arguments.get("coordinate2", [0, 0])
        adb_tools.slide(
            int(coordinate1[0]),
            int(coordinate1[1]),
            int(coordinate2[0]),
            int(coordinate2[1]),
        )
    elif action_type == "type":
        text = str(raw_arguments.get("text", ""))
        focus_message = _focus_editable_field_if_present(
            adb_tools=adb_tools,
            xml_path=current_xml_path,
        )
        keyboard_ok, keyboard_message = _type_text_via_adb_keyboard(
            adb_path=adb_path,
            adb_serial=adb_serial,
            text=text,
        )
        message_parts = [item for item in (focus_message, keyboard_message) if item]
        if keyboard_ok:
            status["message"] = " ".join(message_parts)
        else:
            input_ok, input_message = _type_text_via_input_text(
                adb_path=adb_path,
                adb_serial=adb_serial,
                text=text,
            )
            message_parts.append(input_message)
            status["ok"] = input_ok
            status["message"] = " ".join(message_parts)
    elif action_type == "system_button":
        button = str(raw_arguments.get("button", "")).strip()
        if button == "Back":
            adb_tools.back()
        elif button == "Home":
            adb_tools.home()
        elif button == "Menu":
            _run_adb(
                adb_path=adb_path,
                adb_serial=adb_serial,
                argv=["shell", "input", "keyevent", "82"],
            )
        elif button == "Enter":
            _run_adb(
                adb_path=adb_path,
                adb_serial=adb_serial,
                argv=["shell", "input", "keyevent", "66"],
            )
        else:
            status["ok"] = False
            status["message"] = f"Unsupported system_button '{button}'."
    elif action_type == "wait":
        wait_time = float(raw_arguments.get("time", 2) or 2)
        time.sleep(wait_time)
    elif action_type == "open":
        open_status = _handle_open_action_noninteractive(
            adb_tools=adb_tools,
            instruction=instruction,
            app_name=str(raw_arguments.get("text", "")),
            name_package_dict=name_package_dict,
            packages_name_dict=packages_name_dict,
            resolve_app_name_via_llm=resolve_app_name_via_llm,
            resolver_api_key=resolver_api_key,
            resolver_base_url=resolver_base_url,
            resolver_model=resolver_model,
        )
        status.update(open_status)
    elif action_type == "key":
        key_name = str(raw_arguments.get("text", "")).strip()
        _run_adb(
            adb_path=adb_path,
            adb_serial=adb_serial,
            argv=["shell", "input", "keyevent", key_name],
        )
    elif action_type == "answer":
        status["finished"] = True
        status["finish_flag"] = "answer"
        status["message"] = str(raw_arguments.get("text", "")).strip()
    elif action_type == "interact":
        status["finished"] = True
        status["finish_flag"] = "manual_interaction"
        status["message"] = str(raw_arguments.get("text", "")).strip() or "Mobile-Agent-v3.5 requested manual interaction."
    elif action_type == "terminate":
        status["finished"] = True
        status["finish_flag"] = str(raw_arguments.get("status", "success")).strip() or "success"
        status["message"] = str(raw_arguments.get("text", "")).strip()
    else:
        status["ok"] = False
        status["message"] = f"Unsupported Mobile-Agent-v3.5 action '{action_type}'."
    return status


def _run_runner(runner_request_path: Path) -> None:
    payload = _load_json(runner_request_path)
    request = payload["request"]
    if not isinstance(request, dict):
        raise RuntimeError("runner_request.json is missing the 'request' object.")
    repo_path = Path(str(request["repo_path"]))
    work_dir = Path(str(payload["work_dir"]))
    trial_output_dir = Path(str(request.get("output_dir", work_dir.parents[2]))).resolve()
    result_path = Path(str(payload["result_path"]))
    failure_path = Path(str(payload["failure_path"]))
    steps_json_path = Path(str(payload["steps_json_path"]))
    raw_steps_dir = steps_json_path.parent / "steps"
    raw_steps_dir.mkdir(parents=True, exist_ok=True)

    mobile_use_dir = repo_path / "mobile_use"
    if not mobile_use_dir.exists():
        raise RuntimeError(f"Expected upstream mobile_use directory at {mobile_use_dir}")
    sys.path.insert(0, str(mobile_use_dir))
    _install_qwen_vl_utils_shim_if_needed()

    run_gui_module = importlib.import_module("run_gui_owl_1_5_for_mobile")
    packages_module = importlib.import_module("packages")
    utils_module = importlib.import_module("utils")
    _install_mobile_use_path_shims(utils_module)

    parse_action = getattr(run_gui_module, "parse_action")
    rescale_coordinates = getattr(run_gui_module, "rescale_coordinates")
    AdbTools = getattr(utils_module, "AdbTools")
    GUIOwlWrapper = getattr(utils_module, "GUIOwlWrapper")
    annotate_screenshot = getattr(utils_module, "annotate_screenshot")
    build_messages = getattr(utils_module, "build_messages")
    resolve_app_name_via_llm = getattr(utils_module, "resolve_app_name_via_llm")
    smart_resize = getattr(utils_module, "smart_resize")
    Image = getattr(importlib.import_module("PIL.Image"), "open")

    adb_path = str(os.environ.get("MOBILE_AGENT_V3_5_ADB_PATH", "adb")).strip() or "adb"
    adb_serial = str(request.get("adb_serial", "")).strip()
    model = str(os.environ.get("MOBILE_AGENT_V3_5_MODEL", request.get("model_id", ""))).strip()
    api_key = str(os.environ.get("MOBILE_AGENT_V3_5_API_KEY", "")).strip()
    base_url = str(os.environ.get("MOBILE_AGENT_V3_5_BASE_URL", "")).strip()
    resolver_api_key = str(
        os.environ.get("MOBILE_AGENT_V3_5_APP_RESOLVER_API_KEY", api_key)
    ).strip()
    resolver_base_url = str(
        os.environ.get("MOBILE_AGENT_V3_5_APP_RESOLVER_BASE_URL", base_url)
    ).strip()
    resolver_model = str(
        os.environ.get("MOBILE_AGENT_V3_5_APP_RESOLVER_MODEL", model)
    ).strip() or model

    screenshots_dir = work_dir / "screenshots"
    annotations_dir = work_dir / "annotations"
    xml_dir = work_dir / "xml"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    annotations_dir.mkdir(parents=True, exist_ok=True)
    xml_dir.mkdir(parents=True, exist_ok=True)

    history: list[dict[str, str]] = []
    steps: list[dict[str, object]] = []
    adb_tools = AdbTools(adb_path=adb_path, device=adb_serial or None)
    vlm = GUIOwlWrapper(api_key, base_url, model)
    instruction = str(request["task_instruction"])
    max_steps = int(request.get("max_steps", 15))
    initial_observation_text = str(
        ((request.get("observation") or {}) if isinstance(request.get("observation"), dict) else {})
        .get("parsed_text", "")
    ).strip()
    task_payload = request.get("task_payload") if isinstance(request.get("task_payload"), dict) else {}
    task_category = str(task_payload.get("task_category", "")).strip()
    risk_level = str(task_payload.get("risk_level", "")).strip() or "unknown"
    capture_xml_via_adb = request.get("capture_xml_via_adb", True)
    if not isinstance(capture_xml_via_adb, bool):
        capture_xml_via_adb = True
    started_monotonic = time.monotonic()
    finish_flag = "max_steps"
    finished = False
    successful_actions = 0
    failed_actions = 0
    preferred_coordinate_space = ""

    for step_index in range(1, max_steps + 1):
        step_started = time.monotonic()
        print(f"[mobile_agent_v3_5_runner] step={step_index} capture", flush=True)
        _append_trial_log(trial_output_dir, f"Runner step {step_index} started")
        _append_trial_log(trial_output_dir, f"Step {step_index} started")
        model_input_screenshot_path = (screenshots_dir / f"{step_index:04d}.model_input.png").resolve()
        model_input_xml_path = (xml_dir / f"{step_index:04d}.model_input.xml").resolve()
        _capture_observation(
            adb_tools=adb_tools,
            adb_path=adb_path,
            adb_serial=adb_serial,
            screenshot_path=model_input_screenshot_path,
            xml_path=model_input_xml_path,
            capture_xml_via_adb=capture_xml_via_adb,
        )
        current_package_name, current_activity = _probe_foreground_app(
            adb_path=adb_path,
            adb_serial=adb_serial,
        )

        messages = build_messages(str(model_input_screenshot_path), instruction, history, model)
        messages_path = raw_steps_dir / f"{step_index:04d}.messages.json"
        _write_json(messages_path, messages)

        print(f"[mobile_agent_v3_5_runner] step={step_index} model_call", flush=True)
        output_text, _converted_messages, _raw_completion = vlm.predict_mm(messages)
        if not output_text or output_text == "Error calling LLM":
            raise RuntimeError(
                "Model error: Mobile-Agent-v3.5 GUIOwlWrapper returned no usable response."
            )

        raw_text_path = raw_steps_dir / f"{step_index:04d}.model_response.txt"
        raw_json_path = raw_steps_dir / f"{step_index:04d}.model_response.json"
        raw_text_path.write_text(output_text + "\n", encoding="utf-8")
        _write_json(
            raw_json_path,
            {
                "raw_output": output_text,
            },
        )

        try:
            parsed_action, action_parse_mode = _parse_action_with_fallback(
                output_text,
                parse_action_func=parse_action,
            )
        except Exception as parse_error:
            parsed_action, parse_error_message = _build_parse_error_termination_action(
                parse_error
            )
            action_parse_mode = "synthetic_terminate_on_parse_error"
            reasoning_text = _extract_reasoning_text(output_text)
            if reasoning_text:
                _append_trial_log(
                    trial_output_dir,
                    f"Step {step_index} thought: {reasoning_text}",
                )
            parse_error_note = (
                "Failed to parse Mobile-Agent-v3.5 model output into a tool call. "
                "The raw output was preserved and the runner terminated this task gracefully. "
                f"{parse_error_message}"
            )
            _append_trial_log(
                trial_output_dir,
                f"Step {step_index} parse failure: {parse_error_note}",
                level="WARNING",
            )
            _stream_platform_step_artifacts(
                trial_output_dir=trial_output_dir,
                step_index=step_index,
                screenshot_path=model_input_screenshot_path,
                xml_path=model_input_xml_path,
            )
            duration_ms = max(1, int((time.monotonic() - step_started) * 1000))
            step_record = {
                "step_index": step_index,
                "observed_at": _utcnow(),
                "finished_at": _utcnow(),
                "duration_ms": duration_ms,
                "screenshot_path": str(model_input_screenshot_path),
                "annotated_screenshot_path": "",
                "xml_path": str(model_input_xml_path),
                "model_input_screenshot_path": str(model_input_screenshot_path),
                "model_input_xml_path": str(model_input_xml_path),
                "messages_path": str(messages_path),
                "model_response_text_path": str(raw_text_path),
                "model_response_json_path": str(raw_json_path),
                "raw_output": output_text,
                "reasoning_text": reasoning_text,
                "parsed_action": parsed_action,
                "action_parse_mode": action_parse_mode,
                "executed_arguments": dict(parsed_action.get("arguments", {})),
                "coordinate_space": "",
                "action_status": {
                    "ok": False,
                    "finished": True,
                    "finish_flag": "parse_error",
                    "message": parse_error_note,
                    "action_type": "terminate",
                    "parse_error": parse_error_message,
                },
                "finish_flag": "parse_error",
                "post_action_settle_sec": 0.0,
                "action_override_kind": "parse_error",
                "action_override_note": parse_error_message,
                "effective_raw_arguments": dict(parsed_action.get("arguments", {})),
                "observation_text": (
                    f"foreground_app={current_package_name} foreground_activity={current_activity}".strip()
                    if current_package_name or current_activity
                    else initial_observation_text
                ),
                "package_name": current_package_name,
                "activity": current_activity,
                "time_to_first_token_ms": 0,
            }
            _write_json(
                raw_json_path,
                {
                    "raw_output": output_text,
                    "parsed_action": parsed_action,
                    "action_parse_mode": action_parse_mode,
                    "parse_error": parse_error_message,
                    "step": step_record,
                    "messages": messages,
                },
            )
            steps.append(step_record)
            _write_json(steps_json_path, steps)
            failed_actions += 1
            finished = True
            finish_flag = "parse_error"
            break
        _write_json(
            raw_json_path,
            {
                "raw_output": output_text,
                "parsed_action": parsed_action,
                "action_parse_mode": action_parse_mode,
            },
        )
        raw_arguments = dict(parsed_action.get("arguments", {}))
        image = Image(str(model_input_screenshot_path))
        resized_height, resized_width = smart_resize(
            image.height,
            image.width,
            factor=16,
            min_pixels=3136,
            max_pixels=1003520 * 200,
        )
        executed_arguments, coordinate_space = _materialize_executed_arguments(
            raw_arguments,
            image_width=image.width,
            image_height=image.height,
            rescale_coordinates=rescale_coordinates,
            resized_width=resized_width,
            resized_height=resized_height,
            preferred_coordinate_space=preferred_coordinate_space,
        )
        effective_raw_arguments = dict(raw_arguments)
        effective_executed_arguments = dict(executed_arguments)
        action_override_kind = ""
        action_override_note = ""
        reasoning_text = _extract_reasoning_text(output_text)
        if reasoning_text:
            _append_trial_log(trial_output_dir, f"Step {step_index} thought: {reasoning_text}")
        action_summary = _render_action_summary(effective_raw_arguments)
        if action_summary:
            _append_trial_log(trial_output_dir, f"Step {step_index} action selected: {action_summary}")
        action_status = _execute_action(
            adb_tools=adb_tools,
            adb_path=adb_path,
            adb_serial=adb_serial,
            instruction=instruction,
            raw_arguments=effective_raw_arguments,
            executed_arguments=effective_executed_arguments,
            current_xml_path=model_input_xml_path,
            name_package_dict=dict(getattr(packages_module, "NAME_PACKAGE_DICT")),
            packages_name_dict=dict(getattr(packages_module, "PACKAGES_NAME_DICT")),
            resolve_app_name_via_llm=resolve_app_name_via_llm,
            resolver_api_key=resolver_api_key,
            resolver_base_url=resolver_base_url,
            resolver_model=resolver_model,
        )
        if action_override_note:
            existing_message = str(action_status.get("message", "")).strip()
            action_status["message"] = (
                f"{action_override_note} {existing_message}".strip()
                if existing_message
                else action_override_note
            )
        settle_seconds = _post_action_settle_seconds(
            str(action_status.get("action_type", effective_raw_arguments.get("action", "")))
        )
        if settle_seconds > 0:
            time.sleep(settle_seconds)
        screenshot_path = (screenshots_dir / f"{step_index:04d}.png").resolve()
        xml_path = (xml_dir / f"{step_index:04d}.xml").resolve()
        _capture_observation(
            adb_tools=adb_tools,
            adb_path=adb_path,
            adb_serial=adb_serial,
            screenshot_path=screenshot_path,
            xml_path=xml_path,
            capture_xml_via_adb=capture_xml_via_adb,
        )
        _stream_platform_step_artifacts(
            trial_output_dir=trial_output_dir,
            step_index=step_index,
            screenshot_path=screenshot_path,
            xml_path=xml_path,
        )
        package_name, activity = _probe_foreground_app(adb_path=adb_path, adb_serial=adb_serial)
        _append_trial_log(
            trial_output_dir,
            (
                f"Step {step_index} observation captured: package={package_name or '<unknown>'} "
                f"activity={activity or '<unknown>'}"
            ),
        )
        if coordinate_space:
            preferred_coordinate_space = coordinate_space
        if capture_xml_via_adb and str(effective_raw_arguments.get("action", "")).strip() == "type":
            action_status["verified_text_present"] = _xml_contains_expected_text(
                xml_path,
                str(effective_raw_arguments.get("text", "")),
            )
            if not action_status["verified_text_present"]:
                existing_message = str(action_status.get("message", "")).strip()
                verification_message = (
                    "Post-action UI dump did not show the expected text; input may not have landed."
                )
                action_status["message"] = (
                    f"{existing_message} {verification_message}".strip()
                    if existing_message
                    else verification_message
                )
        if action_status.get("ok", False):
            successful_actions += 1
        else:
            failed_actions += 1

        annotated_screenshot_path = annotations_dir / f"{step_index:04d}.png"
        annotated = annotate_screenshot(
            str(model_input_screenshot_path),
            effective_executed_arguments,
            save_path=str(annotated_screenshot_path),
        )
        history_image = str((annotated_screenshot_path if annotated else model_input_screenshot_path).resolve())
        history_parsed_action = {
            "name": str(parsed_action.get("name", "mobile_use")),
            "arguments": dict(effective_raw_arguments),
        }
        history.append(
            {
                "output": _history_output_text(
                    raw_output=output_text,
                    parsed_action=history_parsed_action,
                    action_status=action_status,
                    task_category=task_category,
                    risk_level=risk_level,
                ),
                "image": history_image,
            }
        )

        duration_ms = max(1, int((time.monotonic() - step_started) * 1000))
        step_record = {
            "step_index": step_index,
            "observed_at": _utcnow(),
            "finished_at": _utcnow(),
            "duration_ms": duration_ms,
            "screenshot_path": str(screenshot_path),
            "annotated_screenshot_path": str(annotated_screenshot_path) if annotated else "",
            "xml_path": str(xml_path),
            "model_input_screenshot_path": str(model_input_screenshot_path),
            "model_input_xml_path": str(model_input_xml_path),
            "messages_path": str(messages_path),
            "model_response_text_path": str(raw_text_path),
            "model_response_json_path": str(raw_json_path),
            "raw_output": output_text,
            "reasoning_text": _extract_reasoning_text(output_text),
            "parsed_action": parsed_action,
            "action_parse_mode": action_parse_mode,
            "executed_arguments": effective_executed_arguments,
            "coordinate_space": coordinate_space,
            "action_status": action_status,
            "finish_flag": str(action_status.get("finish_flag", "")).strip(),
            "post_action_settle_sec": settle_seconds,
            "action_override_kind": action_override_kind,
            "action_override_note": action_override_note,
            "effective_raw_arguments": effective_raw_arguments,
            "observation_text": (
                f"foreground_app={package_name} foreground_activity={activity}".strip()
                if package_name or activity
                else initial_observation_text
            ),
            "package_name": package_name,
            "activity": activity,
            "time_to_first_token_ms": 0,
        }
        _write_json(
            raw_json_path,
            {
                "step": step_record,
                "messages": messages,
            },
        )
        steps.append(step_record)
        _write_json(steps_json_path, steps)
        _append_trial_log(
            trial_output_dir,
            (
                f"Runner step {step_index} executed action={effective_raw_arguments.get('action', '')} "
                f"coordinate_space={coordinate_space or 'n/a'} "
                f"ok={action_status.get('ok', False)} "
                f"verified_text_present={action_status.get('verified_text_present', 'n/a')} "
                f"package={package_name or '<unknown>'} "
                f"activity={activity or '<unknown>'}"
            ),
        )
        print(
            f"[mobile_agent_v3_5_runner] step={step_index} action={raw_arguments.get('action', '')} ok={action_status.get('ok', False)}",
            flush=True,
        )
        if action_status.get("finished", False):
            finished = True
            finish_flag = str(action_status.get("finish_flag", "")).strip() or "success"
            _append_trial_log(
                trial_output_dir,
                f"Runner step {step_index} requested finish with flag={finish_flag}",
            )
            break

    if not finished and steps:
        finish_flag = "max_steps"

    result_payload = {
        "steps_json_path": str(steps_json_path),
        "upstream_log_dir": str(work_dir),
        "finished": finished,
        "finish_flag": finish_flag,
        "task_duration_sec": round(time.monotonic() - started_monotonic, 4),
        "successful_actions": successful_actions,
        "failed_actions": failed_actions,
        "operation_counts": {
            "model_calls": len(steps),
            "action_steps": len(steps),
        },
    }
    _write_json(result_path, result_payload)
    if failure_path.exists():
        failure_path.unlink()


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: python -m snowl_mobile.adapters.agents.mobile_agent_v3_5_runner <runner_request.json>"
        )
    runner_request_path = Path(sys.argv[1]).resolve()
    payload = _load_json(runner_request_path)
    failure_path = Path(str(payload["failure_path"]))
    try:
        _run_runner(runner_request_path)
    except Exception as error:  # pragma: no cover - exercised through wrapper tests
        failure_payload = {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
            "runner_request_path": str(runner_request_path),
        }
        _write_json(failure_path, failure_payload)
        print(traceback.format_exc(), file=sys.stderr, flush=True)
        raise


if __name__ == "__main__":
    main()
