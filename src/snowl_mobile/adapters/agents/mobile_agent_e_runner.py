from __future__ import annotations

import copy
import importlib
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import traceback
import types
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected JSON object at {path}, got {type(payload).__name__}.")
    return payload


def _coerce_step_sleep(value: str) -> float | int:
    parsed = float(value)
    return int(parsed) if parsed.is_integer() else parsed


def _env_flag_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _install_lightweight_stub_modules() -> None:
    class _StubImageFile:
        def __init__(self, path: str | Path) -> None:
            self._path = Path(path)

        @property
        def size(self) -> tuple[int, int]:
            return (1080, 2400)

        def convert(self, _mode: str) -> "_StubImageFile":
            return self

        def save(self, destination: str | Path, _format: str | None = None) -> None:
            destination_path = Path(destination)
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            if self._path.exists():
                destination_path.write_bytes(self._path.read_bytes())
            else:
                destination_path.write_bytes(b"")

    pil_module = types.ModuleType("PIL")
    pil_image_module = types.ModuleType("PIL.Image")
    pil_image_module.open = lambda path: _StubImageFile(path)  # type: ignore[attr-defined]
    pil_draw_module = types.ModuleType("PIL.ImageDraw")
    pil_draw_module.Draw = lambda _image: types.SimpleNamespace(ellipse=lambda *args, **kwargs: None)  # type: ignore[attr-defined]
    pil_module.Image = pil_image_module
    pil_module.ImageDraw = pil_draw_module
    sys.modules.setdefault("PIL", pil_module)
    sys.modules.setdefault("PIL.Image", pil_image_module)
    sys.modules.setdefault("PIL.ImageDraw", pil_draw_module)

    torch_module = types.ModuleType("torch")
    torch_module.Tensor = lambda value: value  # type: ignore[attr-defined]
    sys.modules.setdefault("torch", torch_module)

    numpy_module = types.ModuleType("numpy")
    numpy_module.array = lambda value: value  # type: ignore[attr-defined]
    numpy_module.sum = lambda value, axis=0: value  # type: ignore[attr-defined]
    numpy_module.arctan2 = lambda y, x: 0  # type: ignore[attr-defined]
    numpy_module.argsort = lambda values: list(range(len(values)))  # type: ignore[attr-defined]
    numpy_module.concatenate = lambda values: values[0] if values else []  # type: ignore[attr-defined]
    sys.modules.setdefault("numpy", numpy_module)

    cv2_module = types.ModuleType("cv2")
    cv2_module.imread = lambda _path: None  # type: ignore[attr-defined]
    sys.modules.setdefault("cv2", cv2_module)

    dashscope_module = types.ModuleType("dashscope")
    dashscope_module.api_key = ""

    class _StubMultiModalConversation:
        @staticmethod
        def call(*args, **kwargs) -> dict[str, object]:
            return {"output": {"choices": [{"message": {"content": [{"text": "icon"}]}}]}}

    dashscope_module.MultiModalConversation = _StubMultiModalConversation
    sys.modules.setdefault("dashscope", dashscope_module)

    modelscope_module = types.ModuleType("modelscope")
    modelscope_module.snapshot_download = lambda *args, **kwargs: "/tmp/modelscope-stub"  # type: ignore[attr-defined]

    class _StubGenerationConfig:
        @staticmethod
        def from_pretrained(*args, **kwargs) -> dict[str, object]:
            return {}

    class _StubModel:
        generation_config: dict[str, object] = {}

        def eval(self) -> "_StubModel":
            return self

        def chat(self, *args, **kwargs) -> tuple[str, None]:
            return ("", None)

    class _StubAutoModelForCausalLM:
        @staticmethod
        def from_pretrained(*args, **kwargs) -> _StubModel:
            return _StubModel()

    class _StubAutoTokenizer:
        @staticmethod
        def from_pretrained(*args, **kwargs) -> "_StubAutoTokenizer":
            return _StubAutoTokenizer()

        def from_list_format(self, content: object) -> object:
            return content

    modelscope_module.AutoModelForCausalLM = _StubAutoModelForCausalLM
    modelscope_module.AutoTokenizer = _StubAutoTokenizer
    modelscope_module.GenerationConfig = _StubGenerationConfig

    pipelines_module = types.ModuleType("modelscope.pipelines")
    pipelines_module.pipeline = lambda *args, **kwargs: (lambda *_a, **_k: {})  # type: ignore[attr-defined]

    utils_module = types.ModuleType("modelscope.utils")
    constant_module = types.ModuleType("modelscope.utils.constant")
    constant_module.Tasks = types.SimpleNamespace(
        ocr_detection="ocr_detection",
        ocr_recognition="ocr_recognition",
    )
    utils_module.constant = constant_module

    sys.modules.setdefault("modelscope", modelscope_module)
    sys.modules.setdefault("modelscope.pipelines", pipelines_module)
    sys.modules.setdefault("modelscope.utils", utils_module)
    sys.modules.setdefault("modelscope.utils.constant", constant_module)


def _read_device_dimensions(adb_path: str) -> tuple[int, int]:
    completed = subprocess.run(
        f"{adb_path} shell wm size",
        capture_output=True,
        text=True,
        shell=True,
        check=False,
    )
    match = re.search(r"Physical size:\s*(\d+)x(\d+)", completed.stdout)
    if match is None:
        return (1080, 2400)
    return (int(match.group(1)), int(match.group(2)))


def _dump_ui_hierarchy_xml(adb_path: str, *, xml_path: Path) -> None:
    xml_path.parent.mkdir(parents=True, exist_ok=True)
    device_xml_path = "/sdcard/window_dump.xml"
    dump_result = subprocess.run(
        f"{adb_path} shell uiautomator dump {device_xml_path}",
        capture_output=True,
        text=True,
        shell=True,
        check=False,
    )
    if dump_result.returncode == 0:
        pull_result = subprocess.run(
            f"{adb_path} pull {device_xml_path} {xml_path}",
            capture_output=True,
            text=True,
            shell=True,
            check=False,
        )
        subprocess.run(
            f"{adb_path} shell rm {device_xml_path}",
            capture_output=True,
            text=True,
            shell=True,
            check=False,
        )
        if pull_result.returncode == 0 and xml_path.exists():
            return
    if not xml_path.exists():
        xml_path.write_text("<hierarchy></hierarchy>\n", encoding="utf-8")


def _copy_xml_sidecar_if_present(source_image_path: Path, destination_image_path: Path) -> None:
    source_xml_path = source_image_path.with_suffix(".xml")
    if not source_xml_path.exists():
        return
    destination_xml_path = destination_image_path.with_suffix(".xml")
    try:
        if source_xml_path.resolve() == destination_xml_path.resolve():
            return
    except FileNotFoundError:
        pass
    destination_xml_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_xml_path, destination_xml_path)


def _should_materialize_xml_sidecar(destination: Path) -> bool:
    normalized_parent = destination.parent.name.lower()
    return normalized_parent in {"screenshot", "screenshots"} and destination.suffix.lower() in {
        ".jpg",
        ".jpeg",
        ".png",
    }


class _ImageProxy:
    def __init__(self, inner: object, *, source_path: Path) -> None:
        self._inner = inner
        self._source_path = source_path

    def save(self, destination: str | Path, *args: object, **kwargs: object) -> object:
        result = self._inner.save(destination, *args, **kwargs)
        destination_path = Path(destination)
        if _should_materialize_xml_sidecar(destination_path):
            _copy_xml_sidecar_if_present(self._source_path, destination_path)
        return result

    def convert(self, *args: object, **kwargs: object) -> "_ImageProxy":
        return _ImageProxy(
            self._inner.convert(*args, **kwargs),
            source_path=self._source_path,
        )

    def crop(self, *args: object, **kwargs: object) -> "_ImageProxy":
        return _ImageProxy(
            self._inner.crop(*args, **kwargs),
            source_path=self._source_path,
        )

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)


def _patch_image_save_sidecars(module: object) -> None:
    image_module = getattr(module, "Image", None)
    original_open = getattr(image_module, "open", None)
    if not callable(original_open):
        return

    def _wrapped_open(path: str | Path, *args: object, **kwargs: object) -> _ImageProxy:
        return _ImageProxy(
            original_open(path, *args, **kwargs),
            source_path=Path(path),
        )

    setattr(image_module, "open", _wrapped_open)


def _patch_atomic_screenshot_capture(module: object) -> None:
    try:
        controller_module = importlib.import_module("MobileAgentE.controller")
    except ModuleNotFoundError:
        return

    original_save = getattr(controller_module, "save_screenshot_to_file", None)
    if not callable(original_save):
        return

    def _wrapped_save_screenshot_to_file(adb_path: str, file_path: str = "screenshot.png") -> object:
        saved_path = original_save(adb_path, file_path)
        if saved_path:
            saved_path_obj = Path(str(saved_path))
            if _should_materialize_xml_sidecar(saved_path_obj):
                _dump_ui_hierarchy_xml(
                    adb_path,
                    xml_path=saved_path_obj.with_suffix(".xml"),
                )
        return saved_path

    setattr(controller_module, "save_screenshot_to_file", _wrapped_save_screenshot_to_file)
    try:
        agents_module = importlib.import_module("MobileAgentE.agents")
        setattr(agents_module, "save_screenshot_to_file", _wrapped_save_screenshot_to_file)
    except ModuleNotFoundError:
        pass


def _enable_lightweight_perception(module: object) -> None:
    class _EmptyPolygons:
        shape = (0,)

        def __getitem__(self, _index: int) -> None:
            raise IndexError(_index)

    def _stub_ocr_detection(_image_full: object) -> dict[str, object]:
        return {"polygons": _EmptyPolygons()}

    def _stub_ocr_recognition(_image_crop: object) -> dict[str, list[str]]:
        return {"text": [""]}

    def _lightweight_ocr(
        _screenshot_file: str,
        _ocr_detection: object,
        _ocr_recognition: object,
    ) -> tuple[list[object], list[object]]:
        return ([], [])

    class _LightweightPerceptor:
        def __init__(self, adb_path: str, perception_args: dict[str, object] | None = None) -> None:
            self.adb_path = adb_path
            self.perception_args = perception_args or {}
            self.ocr_detection = _stub_ocr_detection
            self.ocr_recognition = _stub_ocr_recognition
            self.groundingdino_model = None
            self.vlm_model = None
            self.vlm_tokenizer = None

        def get_perception_infos(
            self,
            screenshot_file: str,
            temp_file: str = "temp",
        ) -> tuple[list[dict[str, object]], int, int]:
            screenshot_path = Path(screenshot_file)
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            _capture_screenshot_with_fallback(module, self.adb_path, screenshot_path=screenshot_path)
            width, height = _read_device_dimensions(self.adb_path)
            perception_infos = [
                {
                    "text": "text: lightweight perception fallback active",
                    "coordinates": [width // 2, height // 2],
                }
            ]
            return perception_infos, width, height

    setattr(module, "Perceptor", _LightweightPerceptor)
    setattr(module, "draw_coordinates_on_image", lambda image_path, coordinates: image_path)
    setattr(module, "ocr", _lightweight_ocr)
    setattr(module, "det", lambda screenshot_file, caption, groundingdino_model: [])

    # Mobile-Agent-E imports `ocr` into `MobileAgentE.agents` at module import time, so
    # patch both the upstream definition and the re-exported module-global reference.
    try:
        text_localization_module = importlib.import_module("MobileAgentE.text_localization")
        setattr(text_localization_module, "ocr", _lightweight_ocr)
    except ModuleNotFoundError:
        pass

    try:
        agents_module = importlib.import_module("MobileAgentE.agents")
        setattr(agents_module, "ocr", _lightweight_ocr)
    except ModuleNotFoundError:
        pass


def _capture_screenshot_with_fallback(
    module: object,
    adb_path: str,
    *,
    screenshot_path: Path,
) -> Path:
    screenshot_dir = Path(str(getattr(module, "SCREENSHOT_DIR", "screenshot")))
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)

    save_screenshot = getattr(module, "save_screenshot_to_file", None)
    if callable(save_screenshot):
        png_path = screenshot_dir / "screenshot.png"
        saved_path = save_screenshot(adb_path, file_path=str(png_path))
        if saved_path:
            saved = Path(str(saved_path))
            if saved.exists():
                image_module = getattr(module, "Image", None)
                if hasattr(image_module, "open"):
                    image_module.open(str(saved)).convert("RGB").save(str(screenshot_path), "JPEG")
                elif saved.resolve() != screenshot_path.resolve():
                    shutil.copy2(saved, screenshot_path)
                _dump_ui_hierarchy_xml(adb_path, xml_path=screenshot_path.with_suffix(".xml"))
                if saved.exists() and saved.resolve() != screenshot_path.resolve():
                    saved.unlink()
                return screenshot_path

    original_get_screenshot = getattr(module, "_snowl_original_get_screenshot", None)
    if callable(original_get_screenshot):
        try:
            original_get_screenshot(adb_path)
        except FileNotFoundError:
            # Upstream sometimes raises on removing screenshot.png even after screenshot.jpg
            # was already written successfully into the working directory.
            pass
        fallback_screenshot = screenshot_dir / "screenshot.jpg"
        if fallback_screenshot.exists():
            if fallback_screenshot.resolve() != screenshot_path.resolve():
                shutil.copy2(fallback_screenshot, screenshot_path)
            _dump_ui_hierarchy_xml(adb_path, xml_path=screenshot_path.with_suffix(".xml"))
            return screenshot_path

    raise RuntimeError(
        "Mobile-Agent-E screenshot capture failed to produce the expected screenshot artifact."
    )


def _truncate_text(value: object, *, limit: int = 320) -> str:
    text = str(value).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _normalize_jsonish_text(text: str) -> str:
    normalized = (
        text.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u200b", "")
        .replace("\ufeff", "")
    )
    return normalized.strip()


def _extract_code_block_payloads(text: str) -> list[str]:
    payloads: list[str] = []
    for match in re.finditer(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE):
        payload = _normalize_jsonish_text(match.group(1))
        if payload:
            payloads.append(payload)
    return payloads


def _extract_balanced_json_candidates(text: str, *, opening: str, closing: str) -> list[str]:
    candidates: list[str] = []
    start_index: int | None = None
    depth = 0
    in_string = False
    escape = False

    for index, char in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue

        if char == opening:
            if depth == 0:
                start_index = index
            depth += 1
            continue

        if char == closing and depth > 0:
            depth -= 1
            if depth == 0 and start_index is not None:
                candidate = _normalize_jsonish_text(text[start_index : index + 1])
                if candidate:
                    candidates.append(candidate)
                start_index = None

    return candidates


def _recover_jsonish_object(text: object, *, json_type: str = "dict") -> object:
    if not isinstance(text, str):
        return None
    normalized = _normalize_jsonish_text(text)
    candidates: list[str] = []
    if normalized:
        candidates.append(normalized)
    candidates.extend(_extract_code_block_payloads(normalized))
    if json_type == "list":
        candidates.extend(_extract_balanced_json_candidates(normalized, opening="[", closing="]"))
    else:
        candidates.extend(_extract_balanced_json_candidates(normalized, opening="{", closing="}"))

    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if json_type == "list":
            if isinstance(parsed, list):
                return parsed
        elif isinstance(parsed, dict):
            return parsed
    return None


def _parse_jsonish_scalar(token: str) -> object:
    token = token.strip()
    if not token:
        return ""
    try:
        return json.loads(token)
    except Exception:
        pass
    if re.fullmatch(r"-?\d+", token):
        return int(token)
    if re.fullmatch(r"-?\d+\.\d+", token):
        return float(token)
    return token.strip("\"'")


def _recover_mobile_agent_e_action_object(text: object, *, agents_module: object) -> object:
    if not isinstance(text, str):
        return None
    normalized = _normalize_jsonish_text(text)
    candidates = _extract_balanced_json_candidates(normalized, opening="{", closing="}")
    if normalized:
        candidates.insert(0, normalized)

    signatures = getattr(agents_module, "ATOMIC_ACTION_SIGNITURES", {}) or {}
    shortcuts = getattr(agents_module, "INIT_SHORTCUTS", {}) or {}

    for candidate in candidates:
        if '"name"' not in candidate or '"arguments"' not in candidate:
            continue
        name_match = re.search(r'"name"\s*:\s*"([^"]+)"', candidate)
        if name_match is None:
            continue
        action_name = name_match.group(1).strip()
        expected_keys: list[str] = []
        if isinstance(signatures, dict):
            signature = signatures.get(action_name)
            if isinstance(signature, dict):
                expected_keys = [str(item) for item in signature.get("arguments", []) if item]
        if not expected_keys and isinstance(shortcuts, dict):
            shortcut = shortcuts.get(action_name)
            if isinstance(shortcut, dict):
                expected_keys = [str(item) for item in shortcut.get("arguments", []) if item]

        arguments_null_match = re.search(r'"arguments"\s*:\s*null', candidate)
        if arguments_null_match:
            return {"name": action_name, "arguments": {}}

        arguments_anchor = re.search(r'"arguments"\s*:\s*{', candidate)
        if arguments_anchor is None:
            continue
        opening_index = candidate.find("{", arguments_anchor.start())
        if opening_index < 0:
            continue
        argument_candidates = _extract_balanced_json_candidates(
            candidate[opening_index:],
            opening="{",
            closing="}",
        )
        if not argument_candidates:
            continue
        arguments_block = argument_candidates[0]

        explicit_pattern = re.compile(
            r'"(?P<key>[A-Za-z0-9_]+)"\s*:\s*(?P<value>"(?:\\.|[^"])*"|true|false|null|-?\d+(?:\.\d+)?)',
            flags=re.DOTALL,
        )
        explicit_arguments: dict[str, object] = {}
        for match in explicit_pattern.finditer(arguments_block):
            explicit_arguments[match.group("key")] = _parse_jsonish_scalar(match.group("value"))

        residual = explicit_pattern.sub(" ", arguments_block)
        positional_tokens = re.findall(
            r'"(?:\\.|[^"])*"|true|false|null|-?\d+(?:\.\d+)?',
            residual,
            flags=re.DOTALL,
        )
        positional_arguments = [_parse_jsonish_scalar(token) for token in positional_tokens]

        recovered_arguments: dict[str, object] = {}
        for key in expected_keys:
            if key in explicit_arguments:
                recovered_arguments[key] = explicit_arguments.pop(key)
            elif positional_arguments:
                recovered_arguments[key] = positional_arguments.pop(0)
        for key, value in explicit_arguments.items():
            recovered_arguments[key] = value

        if recovered_arguments or not expected_keys:
            return {
                "name": action_name,
                "arguments": recovered_arguments,
            }
    return None


def _strip_completion_suffix(api_url: str) -> str:
    normalized = api_url.rstrip("/")
    for suffix in ("/chat/completions", "/messages"):
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)]
    return normalized


def _stringify_model_content(content: object) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(str(text))
            elif item:
                parts.append(str(item))
        return "\n".join(part for part in parts if part).strip()
    return str(content)


def _summarize_chat_messages(chat: object) -> list[dict[str, object]]:
    if not isinstance(chat, list):
        return [{"role": "unknown", "summary": _truncate_text(chat)}]

    summarized: list[dict[str, object]] = []
    for item in chat:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            summarized.append({"role": "unknown", "summary": _truncate_text(item)})
            continue
        role = str(item[0])
        content = item[1]
        entry: dict[str, object] = {
            "role": role,
            "content_types": [],
            "text_preview": "",
            "image_count": 0,
        }
        if isinstance(content, list):
            texts: list[str] = []
            content_types: list[str] = []
            image_count = 0
            for piece in content:
                if isinstance(piece, dict):
                    piece_type = str(piece.get("type", "")).strip()
                    if piece_type:
                        content_types.append(piece_type)
                    if piece_type == "text":
                        text = piece.get("text")
                        if text:
                            texts.append(str(text))
                    elif piece_type == "image_url":
                        image_count += 1
                elif piece:
                    texts.append(str(piece))
            entry["content_types"] = content_types
            entry["text_preview"] = _truncate_text("\n".join(texts))
            entry["image_count"] = image_count
        else:
            entry["text_preview"] = _truncate_text(content)
        summarized.append(entry)
    return summarized


def _build_reasoning_payload(
    *,
    chat: object,
    model: str,
    api_url: str,
    token: str | None,
    max_tokens: int,
    temperature: float,
) -> tuple[dict[str, str], dict[str, object]]:
    if token is None:
        raise ValueError("API key is required")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    data: dict[str, object] = {
        "model": model,
        "messages": [],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if not isinstance(chat, list):
        raise ValueError("chat must be a list of role/content pairs")

    if "claude" in model.lower():
        if "47.88.8.18:8088" not in api_url:
            headers = {
                "x-api-key": token,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
        for role, content in chat:
            if role == "system":
                if not isinstance(content, list) or not content:
                    raise ValueError("Claude system message must be a non-empty content list")
                first = content[0]
                if not isinstance(first, dict) or first.get("type") != "text":
                    raise ValueError("Claude system message must start with a text item")
                data["system"] = first["text"]
                continue
            converted_content: list[dict[str, object]] = []
            if not isinstance(content, list):
                raise ValueError("Claude chat content must be a list")
            for item in content:
                if not isinstance(item, dict):
                    raise ValueError("Claude chat items must be objects")
                if item.get("type") == "text":
                    converted_content.append({"type": "text", "text": item["text"]})
                elif item.get("type") == "image_url":
                    converted_content.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": str(item["image_url"]["url"]).replace(
                                    "data:image/jpeg;base64,",
                                    "",
                                ),
                            },
                        }
                    )
                else:
                    raise ValueError(f"Invalid content type: {item.get('type')}")
            data["messages"].append({"role": role, "content": converted_content})
    else:
        for role, content in chat:
            data["messages"].append({"role": role, "content": content})
    return headers, data


def _write_reasoning_diagnostics(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _patch_reasoning_client(module: object, *, diagnostics_path: Path) -> None:
    mobile_agent_api = importlib.import_module("MobileAgentE.api")
    original_inference_chat = getattr(mobile_agent_api, "inference_chat")
    timeout_sec = float(os.environ.get("MOBILE_AGENT_E_REASONING_TIMEOUT_SEC", "60").strip() or "60")

    def _record_failure(
        *,
        transport: str,
        chat: object,
        model: str,
        api_url: str,
        attempt_records: list[dict[str, object]],
        last_error: dict[str, object],
    ) -> None:
        _write_reasoning_diagnostics(
            diagnostics_path,
            {
                "transport": transport,
                "model": model,
                "api_url": api_url,
                "chat_summary": _summarize_chat_messages(chat),
                "timeout_sec": timeout_sec,
                "attempts": attempt_records,
                "last_error": last_error,
            },
        )

    def _openai_sdk_request(
        *,
        chat: object,
        model: str,
        api_url: str,
        token: str | None,
        max_tokens: int,
        temperature: float,
    ) -> str:
        from openai import OpenAI

        _, data = _build_reasoning_payload(
            chat=chat,
            model=model,
            api_url=api_url,
            token=token,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        client = OpenAI(
            base_url=_strip_completion_suffix(api_url),
            api_key=token,
            timeout=timeout_sec,
        )
        response = client.chat.completions.create(
            messages=list(data["messages"]),
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if not getattr(response, "choices", None):
            return ""
        message = response.choices[0].message
        return _stringify_model_content(getattr(message, "content", None))

    def _requests_request(
        *,
        chat: object,
        model: str,
        api_url: str,
        token: str | None,
        usage_tracking_jsonl: str | None,
        max_tokens: int,
        temperature: float,
    ) -> str | None:
        import requests

        headers, data = _build_reasoning_payload(
            chat=chat,
            model=model,
            api_url=api_url,
            token=token,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        max_retry = 5
        sleep_sec = 20
        attempt_records: list[dict[str, object]] = []
        while True:
            attempt_payload: dict[str, object] = {
                "attempt_index": len(attempt_records) + 1,
            }
            try:
                response = requests.post(
                    api_url,
                    headers=headers,
                    json=data if "claude" not in model.lower() else None,
                    data=json.dumps(data) if "claude" in model.lower() else None,
                    timeout=timeout_sec,
                )
                response_text_preview = _truncate_text(response.text, limit=800)
                attempt_payload["status_code"] = response.status_code
                attempt_payload["response_text_preview"] = response_text_preview
                try:
                    response_json = response.json()
                    attempt_payload["response_json_keys"] = (
                        sorted(response_json.keys()) if isinstance(response_json, dict) else []
                    )
                except Exception as parse_error:  # noqa: BLE001
                    response_json = None
                    attempt_payload["response_json_parse_error"] = f"{type(parse_error).__name__}: {parse_error}"

                if response.status_code >= 400:
                    raise RuntimeError(
                        f"HTTP {response.status_code} from reasoning endpoint. "
                        f"body={response_text_preview or '<empty>'}"
                    )

                if "claude" in model.lower():
                    if not isinstance(response_json, dict):
                        raise RuntimeError("Claude response was not a JSON object")
                    content = response_json.get("content")
                    if not isinstance(content, list) or not content:
                        raise RuntimeError(f"Claude response missing content: {response_text_preview}")
                    result = _stringify_model_content(content[0].get("text") if isinstance(content[0], dict) else content[0])
                else:
                    if not isinstance(response_json, dict):
                        raise RuntimeError("OpenAI-compatible response was not a JSON object")
                    choices = response_json.get("choices")
                    if not isinstance(choices, list) or not choices:
                        raise RuntimeError(f"Response missing choices: {response_text_preview}")
                    first_choice = choices[0]
                    if not isinstance(first_choice, dict):
                        raise RuntimeError(f"First choice was not an object: {response_text_preview}")
                    message = first_choice.get("message")
                    if not isinstance(message, dict):
                        raise RuntimeError(f"Choice missing message: {response_text_preview}")
                    result = _stringify_model_content(message.get("content"))

                if not result:
                    raise RuntimeError(f"Response content was empty. body={response_text_preview or '<empty>'}")

                if usage_tracking_jsonl and isinstance(response_json, dict):
                    usage = mobile_agent_api.track_usage(response_json, api_key=token)
                    with open(usage_tracking_jsonl, "a", encoding="utf-8") as usage_handle:
                        usage_handle.write(json.dumps(usage) + "\n")
                return result
            except Exception as error:  # noqa: BLE001
                attempt_payload["exception_type"] = type(error).__name__
                attempt_payload["exception_message"] = str(error)
                attempt_records.append(attempt_payload)
                print("Network Error:")
                print(str(error) or "Request Failed")
            else:
                break
            print(f"Sleep {sleep_sec} before retry...")
            mobile_agent_api.sleep(sleep_sec)
            max_retry -= 1
            if max_retry < 0:
                print(f"Failed after {max_retry} retries...")
                _record_failure(
                    transport="requests",
                    chat=chat,
                    model=model,
                    api_url=api_url,
                    attempt_records=attempt_records,
                    last_error=attempt_records[-1],
                )
                return None
        return None

    def _instrumented_inference_chat(
        chat: object,
        model: str,
        api_url: str,
        token: str | None,
        usage_tracking_jsonl: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.0,
    ) -> str | None:
        backbone_type = str(getattr(module, "BACKBONE_TYPE", "OpenAI"))
        if backbone_type == "OpenAI":
            try:
                result = _openai_sdk_request(
                    chat=chat,
                    model=model,
                    api_url=api_url,
                    token=token,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                if result:
                    return result
            except ModuleNotFoundError:
                pass
            except Exception as sdk_error:  # noqa: BLE001
                _record_failure(
                    transport="openai_sdk",
                    chat=chat,
                    model=model,
                    api_url=api_url,
                    attempt_records=[],
                    last_error={
                        "attempt_index": 1,
                        "exception_type": type(sdk_error).__name__,
                        "exception_message": str(sdk_error),
                    },
                )
        try:
            return _requests_request(
                chat=chat,
                model=model,
                api_url=api_url,
                token=token,
                usage_tracking_jsonl=usage_tracking_jsonl,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception:  # noqa: BLE001
            return original_inference_chat(
                chat,
                model,
                api_url,
                token,
                usage_tracking_jsonl=usage_tracking_jsonl,
                max_tokens=max_tokens,
                temperature=temperature,
            )

    setattr(mobile_agent_api, "inference_chat", _instrumented_inference_chat)
    setattr(module, "inference_chat", _instrumented_inference_chat)


def _active_reasoning_api_url(module: object) -> str:
    backbone_type = str(getattr(module, "BACKBONE_TYPE", "OpenAI"))
    if backbone_type == "OpenAI":
        return str(getattr(module, "OPENAI_API_URL", ""))
    if backbone_type == "Gemini":
        return str(getattr(module, "GEMINI_API_URL", ""))
    if backbone_type == "Claude":
        return str(getattr(module, "CLAUDE_API_URL", ""))
    return ""


def _patch_reasoning_error_guard(module: object, *, diagnostics_path: Path) -> None:
    original = getattr(module, "get_reasoning_model_api_response")

    def _guarded_reasoning_call(
        chat: object,
        model_type: str | None = None,
        model: str | None = None,
        temperature: float = 0.0,
    ) -> str:
        response = original(
            chat,
            model_type=model_type or str(getattr(module, "BACKBONE_TYPE", "OpenAI")),
            model=model,
            temperature=temperature,
        )
        if response is None:
            raise RuntimeError(
                "Model error: Mobile-Agent-E reasoning request returned no response. "
                f"api_url={_active_reasoning_api_url(module)} "
                f"model={model or getattr(module, 'REASONING_MODEL', '')}. "
                "Check base_url, api_key, TLS/connectivity, and upstream provider health. "
                f"Inspect {diagnostics_path} for request diagnostics."
            )
        return str(response)

    setattr(module, "get_reasoning_model_api_response", _guarded_reasoning_call)


def _patch_action_json_extraction() -> None:
    try:
        agents_module = importlib.import_module("MobileAgentE.agents")
    except ModuleNotFoundError:
        return

    original_extract = getattr(agents_module, "extract_json_object", None)
    if not callable(original_extract):
        return

    def _wrapped_extract_json_object(text: object, json_type: str = "dict") -> object:
        parsed = original_extract(text, json_type=json_type)
        if parsed is not None:
            return parsed
        recovered = _recover_jsonish_object(text, json_type=json_type)
        if recovered is not None:
            return recovered
        if json_type == "dict":
            return _recover_mobile_agent_e_action_object(text, agents_module=agents_module)
        return None

    setattr(agents_module, "extract_json_object", _wrapped_extract_json_object)


def _patch_operator_prompt_history_guard() -> None:
    try:
        agents_module = importlib.import_module("MobileAgentE.agents")
    except ModuleNotFoundError:
        return

    operator_cls = getattr(agents_module, "Operator", None)
    original_get_prompt = getattr(operator_cls, "get_prompt", None)
    if not callable(original_get_prompt):
        return

    try:
        source = inspect.getsource(original_get_prompt)
    except (OSError, TypeError):
        return

    marker = (
        'if latest_outcomes[-1] == "C" and "Tap" in action_log_strs[-1] and "Tap" in action_log_strs[-2]:'
    )
    replacement = (
        'if len(action_log_strs) >= 2 and latest_outcomes[-1] == "C" and "Tap" in action_log_strs[-1] '
        'and "Tap" in action_log_strs[-2]:'
    )
    if marker not in source:
        return

    patched_source = source.replace(marker, replacement, 1)
    namespace: dict[str, object] = {}
    exec(textwrap.dedent(patched_source), agents_module.__dict__, namespace)
    patched_get_prompt = namespace.get("get_prompt")
    if callable(patched_get_prompt):
        setattr(operator_cls, "get_prompt", patched_get_prompt)


def _patch_upstream_module(module: object) -> dict[str, object]:
    backbone_type = os.environ.get("BACKBONE_TYPE", "OpenAI").strip() or "OpenAI"
    setattr(module, "BACKBONE_TYPE", backbone_type)

    reasoning_model = os.environ.get("MOBILE_AGENT_E_REASONING_MODEL", "").strip()
    if reasoning_model:
        setattr(module, "REASONING_MODEL", reasoning_model)
        setattr(module, "KNOWLEDGE_REFLECTION_MODEL", reasoning_model)

    reasoning_base_url = os.environ.get("MOBILE_AGENT_E_BASE_URL", "").strip()
    if reasoning_base_url:
        if backbone_type == "OpenAI":
            setattr(module, "OPENAI_API_URL", reasoning_base_url)
        elif backbone_type == "Gemini":
            setattr(module, "GEMINI_API_URL", reasoning_base_url)
        elif backbone_type == "Claude":
            setattr(module, "CLAUDE_API_URL", reasoning_base_url)

    openai_api_key = os.environ.get("OPENAI_API_KEY")
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    claude_api_key = os.environ.get("CLAUDE_API_KEY")
    qwen_api_key = os.environ.get("QWEN_API_KEY")
    if openai_api_key is not None:
        setattr(module, "OPENAI_API_KEY", openai_api_key)
    if gemini_api_key is not None:
        setattr(module, "GEMINI_API_KEY", gemini_api_key)
    if claude_api_key is not None:
        setattr(module, "CLAUDE_API_KEY", claude_api_key)
    if qwen_api_key is not None:
        setattr(module, "QWEN_API_KEY", qwen_api_key)

    caption_call_method = os.environ.get("MOBILE_AGENT_E_CAPTION_CALL_METHOD", "").strip()
    if caption_call_method:
        setattr(module, "CAPTION_CALL_METHOD", caption_call_method)
    caption_model = os.environ.get("MOBILE_AGENT_E_CAPTION_MODEL", "").strip()
    if caption_model:
        setattr(module, "CAPTION_MODEL", caption_model)

    if os.environ.get("MOBILE_AGENT_E_STEP_SLEEP_SEC", "").strip():
        setattr(
            module,
            "SLEEP_BETWEEN_STEPS",
            _coerce_step_sleep(os.environ["MOBILE_AGENT_E_STEP_SLEEP_SEC"]),
        )

    original_get_screenshot = getattr(module, "get_screenshot", None)
    if callable(original_get_screenshot):
        setattr(module, "_snowl_original_get_screenshot", original_get_screenshot)

        def _wrapped_get_screenshot(adb_path: str) -> None:
            screenshot_path = Path(str(getattr(module, "SCREENSHOT_DIR", "screenshot"))) / "screenshot.jpg"
            _capture_screenshot_with_fallback(module, adb_path, screenshot_path=screenshot_path)

        setattr(module, "get_screenshot", _wrapped_get_screenshot)
    _patch_image_save_sidecars(module)
    _patch_atomic_screenshot_capture(module)

    perception_args = copy.deepcopy(getattr(module, "DEFAULT_PERCEPTION_ARGS", {}))
    if not isinstance(perception_args, dict):
        perception_args = {}
    if caption_call_method:
        perception_args["caption_call_method"] = caption_call_method
    if caption_model:
        perception_args["caption_model"] = caption_model
    perception_device = os.environ.get("MOBILE_AGENT_E_PERCEPTION_DEVICE", "").strip()
    if perception_device:
        perception_args["device"] = perception_device

    default_perception_args = getattr(module, "DEFAULT_PERCEPTION_ARGS", None)
    if isinstance(default_perception_args, dict):
        default_perception_args.clear()
        default_perception_args.update(perception_args)
    else:
        setattr(module, "DEFAULT_PERCEPTION_ARGS", perception_args)

    _patch_action_json_extraction()
    _patch_operator_prompt_history_guard()
    if _env_flag_enabled("MOBILE_AGENT_E_LIGHTWEIGHT_PERCEPTION"):
        _enable_lightweight_perception(module)
    return perception_args


def _summarize_steps(steps_payload: list[object]) -> dict[str, Any]:
    operation_counts: dict[str, int] = {}
    successful_actions = 0
    failed_actions = 0
    finish_entry: dict[str, Any] | None = None

    for item in steps_payload:
        if not isinstance(item, dict):
            continue
        operation = str(item.get("operation", "")).strip() or "unknown"
        operation_counts[operation] = operation_counts.get(operation, 0) + 1
        if operation == "action_reflection":
            outcome = str(item.get("outcome", "")).strip().upper()
            if outcome.startswith("A"):
                successful_actions += 1
            elif outcome.startswith(("B", "C")):
                failed_actions += 1
        elif operation == "finish":
            finish_entry = item

    finish_flag = ""
    task_duration_sec = 0.0
    final_info_pool: dict[str, Any] = {}
    if finish_entry is not None:
        finish_flag = str(finish_entry.get("finish_flag", "")).strip()
        try:
            task_duration_sec = float(finish_entry.get("task_duration", 0.0))
        except (TypeError, ValueError):
            task_duration_sec = 0.0
        raw_info_pool = finish_entry.get("final_info_pool", {})
        if isinstance(raw_info_pool, dict):
            final_info_pool = raw_info_pool

    return {
        "operation_counts": operation_counts,
        "successful_actions": successful_actions,
        "failed_actions": failed_actions,
        "finish_flag": finish_flag,
        "finished": bool(finish_flag),
        "task_duration_sec": task_duration_sec,
        "final_info_pool": final_info_pool,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        raise SystemExit("usage: python -m snowl_mobile.adapters.agents.mobile_agent_e_runner <runner_request.json>")

    payload_path = Path(argv[1]).resolve()
    payload = _load_json(payload_path)
    request = payload.get("request", {})
    if not isinstance(request, dict):
        raise RuntimeError("runner request must contain a 'request' object.")

    result_path = Path(str(payload["result_path"])).resolve()
    failure_path = Path(str(payload["failure_path"])).resolve()
    work_dir = Path(str(payload["work_dir"])).resolve()
    upstream_log_root = Path(str(payload["upstream_log_root"])).resolve()
    upstream_run_name = str(payload["upstream_run_name"])
    upstream_task_id = str(payload["upstream_task_id"])

    result_path.parent.mkdir(parents=True, exist_ok=True)
    failure_path.parent.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    upstream_log_root.mkdir(parents=True, exist_ok=True)
    diagnostics_path = failure_path.parent / "reasoning_request_diagnostics.json"
    if diagnostics_path.exists():
        diagnostics_path.unlink()

    try:
        repo_path = Path(str(request["repo_path"])).resolve()
        sys.path.insert(0, str(repo_path))
        os.chdir(work_dir)
        print(f"[runner] repo_path={repo_path}", flush=True)
        print(f"[runner] work_dir={work_dir}", flush=True)

        if _env_flag_enabled("MOBILE_AGENT_E_LIGHTWEIGHT_PERCEPTION"):
            _install_lightweight_stub_modules()
            print("[runner] lightweight perception shim enabled", flush=True)
        else:
            print(
                "[runner] full perception mode enabled; first run may spend minutes downloading "
                "or loading OCR/grounding models before the first step is emitted",
                flush=True,
            )

        module = importlib.import_module("inference_agent_E")
        print("[runner] imported inference_agent_E", flush=True)
        mobile_agent_api = importlib.import_module("MobileAgentE.api")
        setattr(mobile_agent_api, "sleep", lambda seconds: None)
        perception_args = _patch_upstream_module(module)
        _patch_reasoning_client(module, diagnostics_path=diagnostics_path)
        _patch_reasoning_error_guard(module, diagnostics_path=diagnostics_path)
        print(f"[runner] perception_args={perception_args}", flush=True)
        print("[runner] invoking run_single_task", flush=True)

        module.run_single_task(
            instruction=str(request["task_instruction"]),
            run_name=upstream_run_name,
            log_root=str(upstream_log_root),
            task_id=upstream_task_id,
            max_itr=int(request["max_steps"]),
            overwrite_log_dir=True,
            screenrecord=False,
            perception_args=perception_args,
        )

        upstream_log_dir = upstream_log_root / upstream_run_name / upstream_task_id
        steps_json_path = upstream_log_dir / "steps.json"
        if not steps_json_path.exists():
            raise RuntimeError(
                "Mobile-Agent-E completed without emitting steps.json at "
                f"{steps_json_path}."
            )
        steps_payload = json.loads(steps_json_path.read_text(encoding="utf-8"))
        if not isinstance(steps_payload, list):
            raise RuntimeError(
                f"Mobile-Agent-E steps.json must be a JSON list, got {type(steps_payload).__name__}."
            )

        summary = _summarize_steps(steps_payload)
        result_payload = {
            "steps_json_path": str(steps_json_path),
            "upstream_log_dir": str(upstream_log_dir),
            "work_dir": str(work_dir),
            **summary,
        }
        result_path.write_text(
            json.dumps(result_payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return 0
    except Exception as error:
        failure_path.write_text(
            json.dumps(
                {
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                    "traceback": traceback.format_exc(),
                    "runner_request_path": str(payload_path),
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        raise


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
