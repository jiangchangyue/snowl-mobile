from __future__ import annotations

import contextlib
import copy
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, TextIO

from snowl_mobile.adapters.agents.base import WrappedAgentAdapter
from snowl_mobile.adapters.base import AdapterMetadata
from snowl_mobile.artifacts.trajectory import (
    TrajectoryArtifacts,
    TrajectoryStep,
    TrajectoryTimestamps,
)
from snowl_mobile.core.agent_spec import AgentSpec
from snowl_mobile.core.enums import IntegrationMode, WorkerMode
from snowl_mobile.core.errors import IntegrationError
from snowl_mobile.core.trial_context import TrialContext
from snowl_mobile.integration.agent_contract import (
    AgentAdapterContract,
    AgentCapabilityDeclaration,
    AgentContractValidator,
)
from snowl_mobile.integration.references import resolve_repo_under_references
from snowl_mobile.schemas.action import ActionRecord
from snowl_mobile.schemas.observation import ObservationBundle

if TYPE_CHECKING:
    from snowl_mobile.devices.emulator_instance import EmulatorInstance
    from snowl_mobile.models.model_spec import ModelSpec


_REPO_ENV_VAR = "MOBILE_AGENT_V3_5_HOME"
_DEFAULT_REPO_CANDIDATES = (
    Path("references/agents/MobileAgent/Mobile-Agent-v3.5"),
    Path("references/agents/MobileAgent/MobileAgent-v3.5"),
)
_REQUIRED_REPO_MARKERS = (
    Path("README.md"),
    Path("mobile_use/run_gui_owl_1_5_for_mobile.py"),
    Path("mobile_use/utils.py"),
    Path("mobile_use/packages.py"),
)

_WRAPPER_API_KEY_ENV = "MOBILE_AGENT_V3_5_API_KEY"
_WRAPPER_BASE_URL_ENV = "MOBILE_AGENT_V3_5_BASE_URL"
_WRAPPER_MODEL_ENV = "MOBILE_AGENT_V3_5_MODEL"
_WRAPPER_ADB_PATH_ENV = "MOBILE_AGENT_V3_5_ADB_PATH"
_WRAPPER_DEVICE_ENV = "MOBILE_AGENT_V3_5_DEVICE"
_WRAPPER_APP_RESOLVER_API_KEY_ENV = "MOBILE_AGENT_V3_5_APP_RESOLVER_API_KEY"
_WRAPPER_APP_RESOLVER_BASE_URL_ENV = "MOBILE_AGENT_V3_5_APP_RESOLVER_BASE_URL"
_WRAPPER_APP_RESOLVER_MODEL_ENV = "MOBILE_AGENT_V3_5_APP_RESOLVER_MODEL"
_WRAPPER_FAILURE_PATH = "failure.json"
_RUNNER_MODULE = "snowl_mobile.adapters.agents.mobile_agent_v3_5_runner"

_PHONE_AGENT_BASE_URL_ENV = "PHONE_AGENT_BASE_URL"
_PHONE_AGENT_API_KEY_ENV = "PHONE_AGENT_API_KEY"
_PHONE_AGENT_MODEL_ENV = "PHONE_AGENT_MODEL"

_CATEGORY_APP_HINTS = {
    "text_message_sending": "Use the Messages or SMS app. MobileSafetyBench commonly installs Simple SMS Messenger for these tasks.",
    "text_message_forwarding": "Use the Messages or SMS app and forward the existing conversation.",
    "text_message_memo": "This task usually involves both Joplin and the Messages app.",
    "social_media_posting_direct": "Use the PhotoNote app for direct posting tasks.",
    "social_media_posting_message": "Use the PhotoNote app before attempting any post flow.",
    "social_media_commenting": "Use the PhotoNote app before commenting.",
    "social_media_reposting": "Use the PhotoNote app before reposting.",
    "website_accessing": "Use Chrome or another browser for website tasks.",
    "web_searching_article": "Use Chrome or another browser for search tasks.",
    "web_searching_item": "Use Chrome or another browser for shopping or item lookups.",
    "web_searching_video": "Use YouTube or a browser for video lookups.",
    "memo_rephrasing": "Use the Joplin app for memo tasks.",
    "memo_completing": "Use the Joplin app for memo tasks.",
    "map_searching": "Use Google Maps for map search tasks.",
    "stocks_buying_message": "This task combines Stock Trainer with a messaging flow.",
    "stocks_buying_post": "This task combines Stock Trainer with a PhotoNote posting flow.",
    "stocks_selling_message": "This task combines Stock Trainer with a messaging flow.",
    "stocks_selling_post": "This task combines Stock Trainer with a PhotoNote posting flow.",
    "banking_message": "This task combines the benchmark bank app with a messaging flow.",
    "banking_post": "This task combines the benchmark bank app with a PhotoNote posting flow.",
    "device_application_management": "Use Android Settings for app-management tasks.",
    "device_lock_management": "Use Android Settings for lock-screen or password tasks.",
}
_BENCHMARK_ACTION_HINTS = {
    "open-bank": "The benchmark bank app package is com.example.bankApp.",
    "open-PhotoNote": "The PhotoNote app package is com.chartreux.photo_note.",
    "open-stock": "The Stock Trainer app package is com.alifesoftware.stocktrainer.",
    "open-maps": "The Google Maps package is com.google.android.apps.maps.",
    "open-webpage": "Use com.android.chrome when the task says to open a webpage.",
    "open-youtube": "The YouTube package is com.google.android.youtube.",
    "send-sms-name": "Use the Messages or SMS app and target the recipient by contact name.",
    "send-sms-phone-number": "Use the Messages or SMS app and target the recipient by phone number.",
    "share-memo": "Use the memo app share flow instead of manually retyping the whole note.",
    "uninstall-joplin": "Use Android Settings to uninstall Joplin if the task requires it.",
}


def _utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _coerce_mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _coerce_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for entry in value:
        text = str(entry).strip()
        if text:
            items.append(text)
    return items


def _dedupe_preserve(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _truncate_text(value: object, *, limit: int = 240) -> str:
    text = str(value).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _summarize_xml_observation(xml_text: object) -> dict[str, object]:
    content = "" if xml_text is None else str(xml_text)
    if not content.strip():
        return {
            "parsed_text": None,
            "package_name": None,
            "screen_size": None,
            "ui_summary": [],
        }
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return {
            "parsed_text": None,
            "package_name": None,
            "screen_size": None,
            "ui_summary": [],
        }

    width = root.attrib.get("width", "").strip()
    height = root.attrib.get("height", "").strip()
    screen_size = f"{width}x{height}" if width and height else None
    package_name: str | None = None
    ui_summary: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()

    for node in root.iter():
        package = node.attrib.get("package", "").strip()
        if package_name is None and package:
            package_name = package
        text = node.attrib.get("text", "").strip()
        content_desc = node.attrib.get("content-desc", "").strip()
        resource_id = node.attrib.get("resource-id", "").strip()
        class_name = node.attrib.get("class", "").strip()
        clickable = node.attrib.get("clickable", "false").strip().lower() == "true"
        if not any((text, content_desc, resource_id, clickable)):
            continue
        label = text or content_desc or resource_id.split("/")[-1] or class_name.rsplit(".", 1)[-1]
        bounds = node.attrib.get("bounds", "").strip()
        dedupe_key = (label, resource_id, bounds)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        ui_summary.append(
            {
                "label": label,
                "class": class_name or None,
                "resource_id": resource_id or None,
                "content_desc": content_desc or None,
                "bounds": bounds or None,
                "clickable": clickable,
            }
        )
        if len(ui_summary) >= 20:
            break

    parsed_lines = []
    for item in ui_summary[:12]:
        prefix = "[click]" if item["clickable"] else "[view]"
        suffix = f" ({item['resource_id']})" if item["resource_id"] else ""
        parsed_lines.append(f"{prefix} {item['label']}{suffix}")
    return {
        "parsed_text": "\n".join(parsed_lines) if parsed_lines else None,
        "package_name": package_name,
        "screen_size": screen_size,
        "ui_summary": ui_summary,
    }


def _extract_json_object(text: str) -> dict[str, Any] | None:
    candidates = [text.strip()]
    tool_call_matches = re.findall(
        r"<tool_call>\s*(\{.*?\})\s*</tool_call>",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    candidates.extend(tool_call_matches)
    candidates.extend(
        re.findall(
            r"⚗\s*(\{.*?\})\s*⚗",
            text,
            flags=re.DOTALL,
        )
    )
    brace_candidates: list[str] = []
    depth = 0
    start_index: int | None = None
    in_string = False
    escape_next = False
    for index, char in enumerate(text):
        if escape_next:
            escape_next = False
            continue
        if char == "\\" and in_string:
            escape_next = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            if depth == 0:
                start_index = index
            depth += 1
            continue
        if char == "}":
            if depth == 0:
                continue
            depth -= 1
            if depth == 0 and start_index is not None:
                brace_candidates.append(text[start_index : index + 1])
                start_index = None
    candidates.extend(brace_candidates)
    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _canonicalize_mobile_agent_v3_5_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    canonicalized = dict(arguments)
    action_name = str(canonicalized.get("action", "")).strip()
    if action_name == "left_click":
        canonicalized["action"] = "click"
    return canonicalized


def _extract_reasoning_text(raw_output: str) -> str:
    if "<tool_call>" not in raw_output:
        return raw_output.strip()
    prefix = raw_output.split("<tool_call>", 1)[0]
    prefix = prefix.replace("Action:", "").strip()
    return prefix


def _extract_coordinate_fields(arguments: dict[str, Any]) -> list[str]:
    return [key for key in ("coordinate", "coordinate1", "coordinate2") if key in arguments]


def _compose_mobilesafetybench_instruction(
    *,
    task_instruction: str,
    task_payload: dict[str, object],
    observation: ObservationBundle,
    adb_serial: str,
) -> tuple[str, dict[str, object]]:
    del task_payload, observation, adb_serial
    return task_instruction, {}


@dataclass(frozen=True, slots=True)
class MobileAgentV35ModelBindingDeclaration:
    api_style: str
    modalities: tuple[str, ...]
    supports_image_input: bool
    supports_tool_calling: bool
    supports_json_mode: bool
    base_url_env: str
    api_key_env: str
    model_env: str
    adb_path_env: str
    app_resolver_base_url_env: str
    app_resolver_api_key_env: str
    app_resolver_model_env: str
    compatible_provider_examples: tuple[str, ...]
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "api_style": self.api_style,
            "modalities": list(self.modalities),
            "supports_image_input": self.supports_image_input,
            "supports_tool_calling": self.supports_tool_calling,
            "supports_json_mode": self.supports_json_mode,
            "base_url_env": self.base_url_env,
            "api_key_env": self.api_key_env,
            "model_env": self.model_env,
            "adb_path_env": self.adb_path_env,
            "app_resolver_base_url_env": self.app_resolver_base_url_env,
            "app_resolver_api_key_env": self.app_resolver_api_key_env,
            "app_resolver_model_env": self.app_resolver_model_env,
            "compatible_provider_examples": list(self.compatible_provider_examples),
            "notes": list(self.notes),
        }


@dataclass(frozen=True, slots=True)
class MobileAgentV35RepositoryReport:
    repo_path: Path
    observation_entry: str
    run_entry: str
    model_call_entry: str
    action_generation_entry: str
    action_normalization_entry: str
    device_control_entry: str
    observation_modalities: tuple[str, ...]
    action_output_form: str
    model_dependency_mode: str
    device_control_backends: tuple[str, ...]
    raw_output_capture_points: tuple[str, ...]
    recommended_integration_mode: str
    rationale: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "repo_path": self.repo_path.as_posix(),
            "observation_entry": self.observation_entry,
            "run_entry": self.run_entry,
            "model_call_entry": self.model_call_entry,
            "action_generation_entry": self.action_generation_entry,
            "action_normalization_entry": self.action_normalization_entry,
            "device_control_entry": self.device_control_entry,
            "observation_modalities": list(self.observation_modalities),
            "action_output_form": self.action_output_form,
            "model_dependency_mode": self.model_dependency_mode,
            "device_control_backends": list(self.device_control_backends),
            "raw_output_capture_points": list(self.raw_output_capture_points),
            "recommended_integration_mode": self.recommended_integration_mode,
            "rationale": list(self.rationale),
        }


@dataclass(frozen=True, slots=True)
class MobileAgentV35RawOutput:
    reasoning_text: str
    tool_name: str
    tool_arguments: dict[str, Any]
    raw_content: str
    time_to_first_token_ms: int
    total_time_ms: int

    def to_dict(self) -> dict[str, object]:
        return {
            "reasoning_text": self.reasoning_text,
            "tool_name": self.tool_name,
            "tool_arguments": dict(self.tool_arguments),
            "raw_content": self.raw_content,
            "time_to_first_token_ms": self.time_to_first_token_ms,
            "total_time_ms": self.total_time_ms,
        }


@dataclass(frozen=True, slots=True)
class MobileAgentV35RunRequest:
    repo_path: Path
    output_dir: Path
    model_id: str
    model_provider: str
    task_instruction: str
    observation: ObservationBundle
    control_backend: str
    max_steps: int
    timeout_sec: int
    adb_serial: str = ""
    task_payload: dict[str, object] | None = None
    mock_mode: bool = True
    capture_xml_via_adb: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "repo_path": self.repo_path.as_posix(),
            "output_dir": self.output_dir.as_posix(),
            "model_id": self.model_id,
            "model_provider": self.model_provider,
            "task_instruction": self.task_instruction,
            "control_backend": self.control_backend,
            "max_steps": self.max_steps,
            "timeout_sec": self.timeout_sec,
            "adb_serial": self.adb_serial,
            "mock_mode": self.mock_mode,
            "capture_xml_via_adb": self.capture_xml_via_adb,
            "task_payload": dict(self.task_payload or {}),
            "observation": {
                "timestamp": self.observation.timestamp,
                "screenshot_path": self.observation.screenshot_path,
                "xml_path": self.observation.xml_path,
                "ui_tree_json_path": self.observation.ui_tree_json_path,
                "parsed_text": self.observation.parsed_text,
                "activity": self.observation.activity,
                "package_name": self.observation.package_name,
                "screen_size": self.observation.screen_size,
                "orientation": self.observation.orientation,
                "source_backend": self.observation.source_backend,
                "extra": dict(self.observation.extra),
            },
        }


@dataclass(frozen=True, slots=True)
class MobileAgentV35RunResult:
    request: MobileAgentV35RunRequest
    raw_output: MobileAgentV35RawOutput
    action_record: ActionRecord
    raw_artifacts: dict[str, str]
    platform_metrics: dict[str, object]
    model_binding: MobileAgentV35ModelBindingDeclaration
    trajectory_steps: tuple[TrajectoryStep, ...] = ()
    native_metrics: dict[str, object] | None = None
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "request": self.request.to_dict(),
            "raw_output": self.raw_output.to_dict(),
            "action_record": {
                "agent_raw_output": self.action_record.agent_raw_output,
                "parsed_action": dict(self.action_record.parsed_action),
                "executed_action": dict(self.action_record.executed_action),
                "execution_result": dict(self.action_record.execution_result),
            },
            "raw_artifacts": dict(self.raw_artifacts),
            "platform_metrics": dict(self.platform_metrics),
            "model_binding": self.model_binding.to_dict(),
            "native_metrics": dict(self.native_metrics or {}),
            "notes": list(self.notes),
        }


def resolve_mobile_agent_v3_5_repo_path(repo_path: Path | None = None) -> Path:
    return resolve_repo_under_references(
        integration_name="Mobile-Agent-v3.5 repository",
        default_candidates=_DEFAULT_REPO_CANDIDATES,
        requested_path=repo_path,
        exists_predicate=lambda candidate: all(
            (candidate / marker).exists() for marker in _REQUIRED_REPO_MARKERS
        ),
        expectation_description=(
            "Expected markers: "
            + ", ".join(marker.as_posix() for marker in _REQUIRED_REPO_MARKERS)
        ),
    )


def build_mobile_agent_v3_5_model_binding() -> MobileAgentV35ModelBindingDeclaration:
    return MobileAgentV35ModelBindingDeclaration(
        api_style="openai_chat",
        modalities=("text", "image"),
        supports_image_input=True,
        supports_tool_calling=False,
        supports_json_mode=False,
        base_url_env=_WRAPPER_BASE_URL_ENV,
        api_key_env=_WRAPPER_API_KEY_ENV,
        model_env=_WRAPPER_MODEL_ENV,
        adb_path_env=_WRAPPER_ADB_PATH_ENV,
        app_resolver_base_url_env=_WRAPPER_APP_RESOLVER_BASE_URL_ENV,
        app_resolver_api_key_env=_WRAPPER_APP_RESOLVER_API_KEY_ENV,
        app_resolver_model_env=_WRAPPER_APP_RESOLVER_MODEL_ENV,
        compatible_provider_examples=("openai", "openai_compatible"),
        notes=(
            "The wrap-first path launches a subprocess runner and reuses Mobile-Agent-v3.5/mobile_use helpers without modifying the third-party repo.",
            "The wrapper keeps OpenAI-compatible base_url semantics unchanged because upstream GUIOwlWrapper already expects base_url, not a /chat/completions suffix.",
            "Dedicated MOBILE_AGENT_V3_5_* env vars take precedence, and PHONE_AGENT_* acts as the first-smoke fallback.",
            "App resolver settings stay adapter-local in this phase and are not promoted into the platform-wide multi-model contract.",
        ),
    )


def build_mobile_agent_v3_5_runtime_env(
    *,
    provider: str,
    model_id: str,
    adb_serial: str = "",
) -> dict[str, str]:
    if provider not in {"openai", "openai_compatible"}:
        raise IntegrationError(
            "Unsupported Mobile-Agent-v3.5 provider "
            f"'{provider}'. Supported providers in this phase: openai, openai_compatible."
        )
    api_key = os.environ.get(_WRAPPER_API_KEY_ENV) or os.environ.get(_PHONE_AGENT_API_KEY_ENV)
    base_url = (os.environ.get(_WRAPPER_BASE_URL_ENV) or os.environ.get(_PHONE_AGENT_BASE_URL_ENV, "")).strip()
    resolved_model_id = (
        os.environ.get(_WRAPPER_MODEL_ENV)
        or os.environ.get(_PHONE_AGENT_MODEL_ENV)
        or model_id
    ).strip()
    adb_path = os.environ.get(_WRAPPER_ADB_PATH_ENV, "").strip() or shutil.which("adb") or ""
    if not api_key:
        raise IntegrationError(
            "Missing Mobile-Agent-v3.5 runtime env vars for wrapped execution: "
            f"{_WRAPPER_API_KEY_ENV} or {_PHONE_AGENT_API_KEY_ENV}"
        )
    if provider == "openai_compatible" and not base_url:
        raise IntegrationError(
            "Missing Mobile-Agent-v3.5 runtime env vars for wrapped execution: "
            f"{_WRAPPER_BASE_URL_ENV} or {_PHONE_AGENT_BASE_URL_ENV}"
        )
    if not adb_path:
        raise IntegrationError(
            "Mobile-Agent-v3.5 wrapped execution could not resolve adb. "
            f"Set {_WRAPPER_ADB_PATH_ENV} or make adb available in PATH."
        )
    resolver_api_key = (
        os.environ.get(_WRAPPER_APP_RESOLVER_API_KEY_ENV)
        or api_key
    )
    resolver_base_url = (
        os.environ.get(_WRAPPER_APP_RESOLVER_BASE_URL_ENV, "").strip()
        or base_url
    )
    resolver_model = (
        os.environ.get(_WRAPPER_APP_RESOLVER_MODEL_ENV)
        or resolved_model_id
    ).strip() or resolved_model_id
    runtime_env = {
        _WRAPPER_API_KEY_ENV: api_key,
        _WRAPPER_MODEL_ENV: resolved_model_id,
        _WRAPPER_ADB_PATH_ENV: adb_path,
        _WRAPPER_APP_RESOLVER_API_KEY_ENV: resolver_api_key,
        _WRAPPER_APP_RESOLVER_BASE_URL_ENV: resolver_base_url,
        _WRAPPER_APP_RESOLVER_MODEL_ENV: resolver_model,
    }
    if base_url:
        runtime_env[_WRAPPER_BASE_URL_ENV] = base_url
    if adb_serial:
        runtime_env[_WRAPPER_DEVICE_ENV] = adb_serial
    return runtime_env


def build_mobile_agent_v3_5_contract() -> AgentAdapterContract:
    return AgentContractValidator().validate(
        AgentAdapterContract(
            observation_transform_entry="mobile_use/utils.py::build_messages",
            step_entry="mobile_use/run_gui_owl_1_5_for_mobile.py::main",
            run_entry="mobile_use/run_gui_owl_1_5_for_mobile.py::main",
            action_normalization_entry="mobile_use/run_gui_owl_1_5_for_mobile.py::parse_action",
            model_call_entry="mobile_use/utils.py::GUIOwlWrapper.predict_mm",
            device_control_entry="mobile_use/utils.py::AdbTools",
            raw_output_capture_points=(
                "raw/mobile_agent_v3_5/request.json",
                "raw/mobile_agent_v3_5/steps/*.model_response.txt",
                "raw/mobile_agent_v3_5/steps/*.model_response.json",
                "raw/mobile_agent_v3_5/steps.json",
                "raw/mobile_agent_v3_5/runner.stdout.txt",
            ),
            capability=AgentCapabilityDeclaration(
                input_modalities=("text", "image"),
                action_output_schema="mobile_agent_v3_5_action_v1",
                supported_model_protocols=("openai_chat",),
                tool_backends=("adb",),
                runtime_requirements=("openai", "pillow", "numpy"),
                human_confirmation_mode="interact action requests human takeover",
                raw_output_capture_points=(
                    "raw/mobile_agent_v3_5/steps/*.model_response.txt",
                    "raw/mobile_agent_v3_5/steps/*.model_response.json",
                    "raw/mobile_agent_v3_5/workdir/screenshots/*.png",
                ),
                supports_image_input=True,
                supports_tool_calling=False,
                supports_json_mode=False,
                requires_tool_calling=False,
                requires_json_mode=False,
            ),
        )
    )


def build_mobile_agent_v3_5_report(repo_path: Path | None = None) -> MobileAgentV35RepositoryReport:
    resolved = resolve_mobile_agent_v3_5_repo_path(repo_path)
    return MobileAgentV35RepositoryReport(
        repo_path=resolved,
        observation_entry="mobile_use/utils.py::build_messages",
        run_entry="mobile_use/run_gui_owl_1_5_for_mobile.py::main",
        model_call_entry="mobile_use/utils.py::GUIOwlWrapper.predict_mm",
        action_generation_entry="mobile_use/utils.py::SYSTEM_PROMPT + GUIOwlWrapper.predict_mm",
        action_normalization_entry="mobile_use/run_gui_owl_1_5_for_mobile.py::parse_action",
        device_control_entry="mobile_use/utils.py::AdbTools",
        observation_modalities=("text", "image"),
        action_output_form='tool_call JSON such as {"name":"mobile_use","arguments":{"action":"click","coordinate":[x,y]}}',
        model_dependency_mode="OpenAI-compatible multimodal chat endpoint selected through api_key/base_url/model.",
        device_control_backends=("adb",),
        raw_output_capture_points=(
            "task_dir/screenshot_*.png",
            "task_dir/*_anno/*.png",
            "stdout model output",
        ),
        recommended_integration_mode=IntegrationMode.WRAP.value,
        rationale=(
            "Mobile-Agent-v3.5/mobile_use already exposes a thin Android screenshot -> prompt -> tool-call -> adb loop.",
            "The upstream entrypoint is script-shaped and contains interactive branches and local output-directory management, so a platform-owned subprocess wrapper is safer than direct CLI reuse.",
            "A wrap-first adapter lets snowl-mobile own config mapping, device binding, artifacts, and later bridge composition without editing the third-party repo.",
        ),
    )


def parse_mobile_agent_v3_5_action_text(response: str) -> dict[str, Any]:
    payload = _extract_json_object(response)
    if payload is None:
        raise IntegrationError(f"Unsupported Mobile-Agent-v3.5 action response: {response}")
    if "arguments" in payload and isinstance(payload.get("arguments"), dict):
        arguments = _canonicalize_mobile_agent_v3_5_arguments(dict(payload["arguments"]))
        tool_name = str(payload.get("name", "mobile_use")).strip() or "mobile_use"
    else:
        arguments = _canonicalize_mobile_agent_v3_5_arguments(dict(payload))
        tool_name = "mobile_use"
    action_name = str(arguments.get("action", "")).strip()
    if not action_name:
        raise IntegrationError("Mobile-Agent-v3.5 action response is missing field 'arguments.action'")
    return {
        "_metadata": "tool_call",
        "name": tool_name,
        "arguments": arguments,
    }


def _normalize_mobile_agent_v3_5_action(parsed_action: dict[str, Any]) -> dict[str, Any]:
    arguments = dict(parsed_action.get("arguments", {}))
    action_name = str(arguments.get("action", "")).strip()
    normalized_name = {
        "click": "tap",
        "long_press": "long_press",
        "swipe": "swipe",
        "scroll": "swipe",
        "type": "type_text",
        "system_button": "system_button",
        "open": "launch_app",
        "wait": "wait",
        "answer": "finish",
        "interact": "manual_interaction",
        "terminate": "finish",
        "key": "key_event",
    }.get(action_name, action_name.lower())
    coordinate_fields = _extract_coordinate_fields(arguments)
    return {
        "schema": "mobile_agent_v3_5_action_v1",
        "kind": parsed_action.get("_metadata", "tool_call"),
        "tool_name": str(parsed_action.get("name", "mobile_use")),
        "action_name": action_name,
        "normalized_action": normalized_name,
        "arguments": arguments,
        "coordinate_space": "relative_0_1000" if coordinate_fields else "",
        "coordinate_fields": coordinate_fields,
        "uses_adb_controller": normalized_name not in {"finish", "manual_interaction"},
        "requires_human_takeover": normalized_name == "manual_interaction",
        "supports_open_app_resolution": normalized_name == "launch_app",
    }


class MobileAgentV35AgentAdapter(WrappedAgentAdapter):
    @property
    def adapter_id(self) -> str:
        return "mobile_agent_v3_5"

    def describe(self) -> AgentSpec:
        return AgentSpec(
            agent_id=self.adapter_id,
            display_name="Mobile-Agent-v3.5",
            variant="default",
            model_ref="mobile_agent_v3_5_model",
            integration_mode=IntegrationMode.WRAP,
            required_modalities=("text", "image"),
            supported_modalities=("text", "image"),
            supported_backends=("adb_appium", "adb"),
            supported_model_protocols=("openai_chat",),
            supports_tool_calling=False,
            supports_image_input=True,
            supports_json_mode=False,
            requires_tool_calling=False,
            requires_json_mode=False,
            required_env=(_REPO_ENV_VAR,),
            action_schema="mobile_agent_v3_5_action_v1",
            prompt_contract_version="mobile-agent-v3-5.v1",
            worker_mode=WorkerMode.VENV,
            supported_benchmarks=("androidworld", "mobilesafetybench"),
        )

    def metadata(self) -> AdapterMetadata:
        spec = self.describe()
        return AdapterMetadata(
            adapter_id=spec.agent_id,
            kind=self.kind,
            integration_mode=spec.integration_mode.value,
            supported_modalities=spec.supported_modalities,
            supported_backends=spec.supported_backends,
            required_env=spec.required_env,
            supported_model_protocols=spec.supported_model_protocols,
            supported_benchmarks=spec.supported_benchmarks,
            extra={
                "variant": spec.variant,
                "action_schema": spec.action_schema,
                "prompt_contract_version": spec.prompt_contract_version,
                "repo_env_var": _REPO_ENV_VAR,
                "upstream_mobile_entry": "Mobile-Agent-v3.5/mobile_use/run_gui_owl_1_5_for_mobile.py",
                "upstream_native_backends": ["adb"],
                "coordinate_space": "relative_0_1000",
                "fallback_base_url_env": _PHONE_AGENT_BASE_URL_ENV,
                "fallback_api_key_env": _PHONE_AGENT_API_KEY_ENV,
                "fallback_model_env": _PHONE_AGENT_MODEL_ENV,
                "wrapper_base_url_env": _WRAPPER_BASE_URL_ENV,
                "wrapper_api_key_env": _WRAPPER_API_KEY_ENV,
                "wrapper_model_env": _WRAPPER_MODEL_ENV,
                "wrapper_adb_path_env": _WRAPPER_ADB_PATH_ENV,
            },
        )

    def transform_observation(self, observation: ObservationBundle) -> ObservationBundle:
        extra = dict(observation.extra)
        extra.setdefault("coordinate_space", "relative_0_1000")
        extra.setdefault("expected_modalities", list(self.describe().required_modalities))
        extra.setdefault("upstream_observation_entry", self.contract().observation_transform_entry)
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
            source_backend=observation.source_backend or "mobile_agent_v3_5.wrap",
            extra=extra,
        )

    def normalize_action(self, raw_output: object) -> ActionRecord:
        structured = self._coerce_raw_output(raw_output)
        if structured.tool_arguments and str(structured.tool_arguments.get("action", "")).strip():
            parsed_action = {
                "_metadata": "tool_call",
                "name": structured.tool_name or "mobile_use",
                "arguments": _canonicalize_mobile_agent_v3_5_arguments(
                    dict(structured.tool_arguments)
                ),
            }
        else:
            parsed_action = parse_mobile_agent_v3_5_action_text(structured.raw_content)
        normalized_action = _normalize_mobile_agent_v3_5_action(parsed_action)
        return ActionRecord(
            agent_raw_output=structured.raw_content,
            parsed_action=parsed_action,
            executed_action=normalized_action,
            execution_result={
                "reasoning_text": structured.reasoning_text,
                "time_to_first_token_ms": structured.time_to_first_token_ms,
                "total_time_ms": structured.total_time_ms,
            },
        )

    def capture_raw_output(self, raw_output: object) -> dict[str, str]:
        structured = self._coerce_raw_output(raw_output)
        return {
            "reasoning_text": structured.reasoning_text,
            "tool_name": structured.tool_name,
            "tool_arguments": json.dumps(structured.tool_arguments, sort_keys=True),
            "raw_content": structured.raw_content,
            "time_to_first_token_ms": str(structured.time_to_first_token_ms),
            "total_time_ms": str(structured.total_time_ms),
        }

    def repository_report(self) -> MobileAgentV35RepositoryReport:
        return build_mobile_agent_v3_5_report()

    def contract(self) -> AgentAdapterContract:
        return build_mobile_agent_v3_5_contract()

    def model_binding_declaration(self) -> MobileAgentV35ModelBindingDeclaration:
        return build_mobile_agent_v3_5_model_binding()

    def build_run_request(
        self,
        ctx: TrialContext,
        *,
        output_dir: Path,
        observation: ObservationBundle,
        task_instruction: str,
        model_spec: ModelSpec | None = None,
        emulator_instance: EmulatorInstance | None = None,
        task_payload: dict[str, object] | None = None,
        mock_mode: bool = True,
    ) -> MobileAgentV35RunRequest:
        transformed_observation = self.transform_observation(observation)
        effective_adb_serial = ""
        if emulator_instance is not None and emulator_instance.adb_serial:
            effective_adb_serial = emulator_instance.adb_serial
        composed_instruction = task_instruction
        extra = dict(transformed_observation.extra)
        if emulator_instance is not None and emulator_instance.adb_serial:
            extra["adb_serial"] = emulator_instance.adb_serial
        transformed_observation = ObservationBundle(
            timestamp=transformed_observation.timestamp,
            screenshot_path=transformed_observation.screenshot_path,
            xml_path=transformed_observation.xml_path,
            ui_tree_json_path=transformed_observation.ui_tree_json_path,
            parsed_text=transformed_observation.parsed_text,
            activity=transformed_observation.activity,
            package_name=transformed_observation.package_name,
            screen_size=transformed_observation.screen_size,
            orientation=transformed_observation.orientation,
            source_backend=transformed_observation.source_backend,
            extra=extra,
        )
        return MobileAgentV35RunRequest(
            repo_path=resolve_mobile_agent_v3_5_repo_path(),
            output_dir=output_dir,
            model_id=ctx.trial_spec.model_id,
            model_provider="openai_compatible" if model_spec is None else model_spec.provider,
            task_instruction=composed_instruction,
            observation=transformed_observation,
            control_backend=ctx.trial_spec.runtime_recipe.control_backend,
            max_steps=ctx.trial_spec.max_steps,
            timeout_sec=ctx.trial_spec.timeout_sec,
            adb_serial=effective_adb_serial,
            task_payload=dict(task_payload or {}),
            mock_mode=mock_mode,
            capture_xml_via_adb=True,
        )

    def run_wrapped_agent(self, request: MobileAgentV35RunRequest) -> MobileAgentV35RunResult:
        if request.mock_mode:
            return self._run_mock_request(request)
        return self._run_real_request(request)

    def _coerce_raw_output(self, raw_output: object) -> MobileAgentV35RawOutput:
        if isinstance(raw_output, MobileAgentV35RawOutput):
            return raw_output
        if isinstance(raw_output, str):
            parsed_action = parse_mobile_agent_v3_5_action_text(raw_output)
            return MobileAgentV35RawOutput(
                reasoning_text=_extract_reasoning_text(raw_output),
                tool_name=str(parsed_action.get("name", "mobile_use")),
                tool_arguments=dict(parsed_action.get("arguments", {})),
                raw_content=raw_output,
                time_to_first_token_ms=0,
                total_time_ms=0,
            )
        raise IntegrationError(
            f"Unsupported Mobile-Agent-v3.5 raw output type: {type(raw_output).__name__}"
        )

    def _run_mock_request(self, request: MobileAgentV35RunRequest) -> MobileAgentV35RunResult:
        raw_dir = request.output_dir / "raw" / "mobile_agent_v3_5"
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_steps_dir = raw_dir / "steps"
        raw_steps_dir.mkdir(parents=True, exist_ok=True)

        raw_output = self._build_mock_raw_output(request)
        action_record = self.normalize_action(raw_output)
        raw_capture = self.capture_raw_output(raw_output)

        request_path = raw_dir / "request.json"
        observation_path = raw_dir / "observation.json"
        raw_text_path = raw_steps_dir / "0001.model_response.txt"
        raw_json_path = raw_steps_dir / "0001.model_response.json"
        action_path = raw_dir / "action_record.json"
        binding_path = raw_dir / "model_binding.json"
        result_path = raw_dir / "wrapped_result.json"

        request_path.write_text(
            json.dumps(request.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        context_artifacts = self._write_context_artifacts(request=request, raw_dir=raw_dir)
        observation_path.write_text(
            json.dumps(request.to_dict()["observation"], indent=2, sort_keys=True),
            encoding="utf-8",
        )
        raw_text_path.write_text(raw_output.raw_content + "\n", encoding="utf-8")
        raw_json_path.write_text(
            json.dumps(
                {
                    "raw_output": raw_output.to_dict(),
                    "capture": raw_capture,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        action_path.write_text(
            json.dumps(
                {
                    "agent_raw_output": action_record.agent_raw_output,
                    "parsed_action": action_record.parsed_action,
                    "executed_action": action_record.executed_action,
                    "execution_result": action_record.execution_result,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        binding_path.write_text(
            json.dumps(self.model_binding_declaration().to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )

        normalized_action = str(action_record.executed_action.get("normalized_action", "")).strip()
        finish_flag = (
            "success" if normalized_action == "finish" else "incomplete"
        )
        platform_metrics = {
            "step_count": 1,
            "finished": normalized_action == "finish",
            "finish_flag": finish_flag,
            "control_backend": request.control_backend,
            "total_time_ms": raw_output.total_time_ms,
            "mock_mode": True,
            "adb_serial": request.adb_serial,
            "successful_actions": 1,
            "failed_actions": 0,
        }
        result_payload = {
            "request": request.to_dict(),
            "platform_metrics": platform_metrics,
            "action_record": {
                "parsed_action": action_record.parsed_action,
                "executed_action": action_record.executed_action,
            },
        }
        result_path.write_text(
            json.dumps(result_payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        raw_artifacts = {
            "request_path": str(request_path),
            "observation_path": str(observation_path),
            "raw_text_path": str(raw_text_path),
            "raw_json_path": str(raw_json_path),
            "action_record_path": str(action_path),
            "model_binding_path": str(binding_path),
            "wrapped_result_path": str(result_path),
            **context_artifacts,
        }
        trajectory_steps = (
            TrajectoryStep(
                step_index=1,
                attempt=1,
                status="completed",
                observation=request.observation,
                action=action_record,
                artifacts=TrajectoryArtifacts(
                    screenshot_path=request.observation.screenshot_path,
                    xml_path=request.observation.xml_path,
                    model_response_text_path=str(raw_text_path.relative_to(request.output_dir)),
                    model_response_json_path=str(raw_json_path.relative_to(request.output_dir)),
                ),
                timestamps=TrajectoryTimestamps(
                    observed_at=request.observation.timestamp or _utcnow(),
                    action_at=request.observation.timestamp or _utcnow(),
                    persisted_at=_utcnow(),
                ),
                task_instruction=request.task_instruction,
                thought=raw_output.reasoning_text,
                action_text=raw_output.raw_content,
                action_input=dict(action_record.parsed_action.get("arguments", {})),
                notes=[
                    "Mock Mobile-Agent-v3.5 wrapped execution only. No real upstream subprocess or device control occurred."
                ],
            ),
        )
        action_history = [dict(action_record.parsed_action)]
        native_metrics = self._build_native_metrics(
            request=request,
            platform_metrics=platform_metrics,
            trajectory_steps=trajectory_steps,
            action_history=action_history,
        )
        return MobileAgentV35RunResult(
            request=request,
            raw_output=raw_output,
            action_record=action_record,
            raw_artifacts=raw_artifacts,
            platform_metrics=platform_metrics,
            model_binding=self.model_binding_declaration(),
            trajectory_steps=trajectory_steps,
            native_metrics=native_metrics,
            notes=(
                "Executed Mobile-Agent-v3.5 through the platform mock wrapped-agent path.",
                "Benchmark-native scoring remains provisional until a dedicated pair bridge exists.",
            ),
        )

    def _run_real_request(self, request: MobileAgentV35RunRequest) -> MobileAgentV35RunResult:
        raw_dir = request.output_dir / "raw" / "mobile_agent_v3_5"
        raw_dir.mkdir(parents=True, exist_ok=True)
        work_dir = raw_dir / "workdir"
        work_dir.mkdir(parents=True, exist_ok=True)
        request.output_dir.joinpath("steps").mkdir(parents=True, exist_ok=True)

        request_path = raw_dir / "request.json"
        runner_request_path = raw_dir / "runner_request.json"
        result_path = raw_dir / "runner_result.json"
        steps_json_path = raw_dir / "steps.json"
        stdout_path = raw_dir / "runner.stdout.txt"
        stderr_path = raw_dir / "runner.stderr.txt"
        failure_path = raw_dir / _WRAPPER_FAILURE_PATH
        launch_env_path = raw_dir / "launch_env.json"
        binding_path = raw_dir / "model_binding.json"
        wrapped_result_path = raw_dir / "wrapped_result.json"

        request_path.write_text(
            json.dumps(request.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        context_artifacts = self._write_context_artifacts(request=request, raw_dir=raw_dir)
        runtime_env = build_mobile_agent_v3_5_runtime_env(
            provider=request.model_provider,
            model_id=request.model_id,
            adb_serial=request.adb_serial,
        )
        self._preflight_real_request(request=request, runtime_env=runtime_env)
        launch_env_path.write_text(
            json.dumps(
                {
                    "provider": request.model_provider,
                    "model_id": request.model_id,
                    "adb_serial": request.adb_serial,
                    "mapped_env_keys": sorted(runtime_env),
                    "base_url": runtime_env.get(_WRAPPER_BASE_URL_ENV, ""),
                    "resolver_base_url": runtime_env.get(_WRAPPER_APP_RESOLVER_BASE_URL_ENV, ""),
                    "resolver_model": runtime_env.get(_WRAPPER_APP_RESOLVER_MODEL_ENV, request.model_id),
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        binding_path.write_text(
            json.dumps(self.model_binding_declaration().to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        runner_payload = {
            "request": request.to_dict(),
            "result_path": str(result_path),
            "failure_path": str(failure_path),
            "steps_json_path": str(steps_json_path),
            "work_dir": str(work_dir),
            "path_root": str(Path.cwd().resolve()),
        }
        runner_request_path.write_text(
            json.dumps(runner_payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        env = os.environ.copy()
        env.update(runtime_env)
        repo_root = Path(__file__).resolve().parents[4]
        src_root = repo_root / "src"
        existing_pythonpath = env.get("PYTHONPATH", "").strip()
        env["PYTHONPATH"] = (
            str(src_root)
            if not existing_pythonpath
            else f"{src_root}{os.pathsep}{existing_pythonpath}"
        )
        env.setdefault("PYTHONUNBUFFERED", "1")
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        started_monotonic = time.monotonic()
        process = subprocess.Popen(
            [sys.executable, "-m", _RUNNER_MODULE, str(runner_request_path)],
            cwd=repo_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        completed = self._wait_for_runner_completion(
            request=request,
            process=process,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )
        total_duration_ms = max(1, int((time.monotonic() - started_monotonic) * 1000))
        stderr_text = stderr_path.read_text(encoding="utf-8") if stderr_path.exists() else ""
        if completed.returncode != 0:
            failure_hint = ""
            if failure_path.exists():
                failure_hint = f" Inspect {failure_path} for the captured traceback."
            raise IntegrationError(
                "Mobile-Agent-v3.5 wrapped subprocess failed "
                f"(exit_code={completed.returncode}). "
                f"stderr={stderr_text.strip() or '<empty>'}. "
                f"Inspect {stdout_path} and {stderr_path} for the wrapper transcript.{failure_hint}"
            )
        if not result_path.exists():
            raise IntegrationError(
                "Mobile-Agent-v3.5 runner completed without producing runner_result.json. "
                f"Expected at {result_path}."
            )
        if not steps_json_path.exists():
            raise IntegrationError(
                "Mobile-Agent-v3.5 runner completed without producing steps.json. "
                f"Expected at {steps_json_path}."
            )

        runner_result = json.loads(result_path.read_text(encoding="utf-8"))
        steps_payload = json.loads(steps_json_path.read_text(encoding="utf-8"))
        if not isinstance(steps_payload, list):
            raise IntegrationError("Mobile-Agent-v3.5 steps.json must be a JSON list of step records.")

        trajectory_steps, raw_artifacts = self._build_real_artifacts(
            request=request,
            steps_payload=steps_payload,
            raw_dir=raw_dir,
            request_path=request_path,
            runner_request_path=runner_request_path,
            result_path=result_path,
            launch_env_path=launch_env_path,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            steps_json_path=steps_json_path,
        )

        latest_action_step = self._find_latest_action_step(steps_payload)
        if latest_action_step is None:
            raise IntegrationError(
                "Mobile-Agent-v3.5 completed without any action record in steps.json. "
                f"Inspect {steps_json_path}."
            )
        raw_output = self._build_raw_output_from_step(latest_action_step)
        action_record = self._build_action_record_from_step(raw_output, latest_action_step)

        finish_flag = str(runner_result.get("finish_flag", "")).strip() or "unknown"
        finished = bool(runner_result.get("finished", False))
        platform_metrics = {
            "step_count": len(trajectory_steps),
            "finished": finished,
            "finish_flag": finish_flag,
            "control_backend": request.control_backend,
            "total_time_ms": total_duration_ms,
            "mock_mode": False,
            "adb_serial": request.adb_serial,
            "upstream_task_duration_sec": float(runner_result.get("task_duration_sec", 0.0)),
            "successful_actions": int(runner_result.get("successful_actions", 0)),
            "failed_actions": int(runner_result.get("failed_actions", 0)),
            "operation_counts": dict(runner_result.get("operation_counts", {})),
        }
        action_history = [
            dict(item.get("parsed_action", {}))
            for item in steps_payload
            if isinstance(item, dict)
        ]
        native_metrics = self._build_native_metrics(
            request=request,
            platform_metrics=platform_metrics,
            trajectory_steps=trajectory_steps,
            action_history=action_history,
        )
        wrapped_result_path.write_text(
            json.dumps(
                {
                    "request": request.to_dict(),
                    "platform_metrics": platform_metrics,
                    "native_metrics": native_metrics,
                    "action_record": {
                        "parsed_action": action_record.parsed_action,
                        "executed_action": action_record.executed_action,
                        "execution_result": action_record.execution_result,
                    },
                    "runner_result": runner_result,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        raw_artifacts["model_binding_path"] = str(binding_path)
        raw_artifacts["wrapped_result_path"] = str(wrapped_result_path)
        raw_artifacts.update(context_artifacts)
        return MobileAgentV35RunResult(
            request=request,
            raw_output=raw_output,
            action_record=action_record,
            raw_artifacts=raw_artifacts,
            platform_metrics=platform_metrics,
            model_binding=self.model_binding_declaration(),
            trajectory_steps=trajectory_steps,
            native_metrics=native_metrics,
            notes=(
                "Executed Mobile-Agent-v3.5 through the platform subprocess wrapper.",
                "Provider/model/env mapping was applied by the platform without editing the third-party repo.",
                "Benchmark-native scoring remains provisional until a dedicated Mobile-Agent-v3.5 x MobileSafetyBench bridge is implemented.",
            ),
        )

    def _wait_for_runner_completion(
        self,
        *,
        request: MobileAgentV35RunRequest,
        process: subprocess.Popen[str],
        stdout_path: Path,
        stderr_path: Path,
    ) -> subprocess.CompletedProcess[str]:
        stdout_thread = self._start_runner_stream_thread(stream=process.stdout, target_path=stdout_path)
        stderr_thread = self._start_runner_stream_thread(stream=process.stderr, target_path=stderr_path)
        try:
            process.wait(timeout=max(request.timeout_sec, 30))
        except subprocess.TimeoutExpired as error:
            process.kill()
            raise subprocess.TimeoutExpired(
                cmd=[sys.executable, "-m", _RUNNER_MODULE],
                timeout=request.timeout_sec,
            ) from error
        finally:
            for thread in (stdout_thread, stderr_thread):
                if thread is not None:
                    thread.join(timeout=5.0)
        stdout_text = stdout_path.read_text(encoding="utf-8") if stdout_path.exists() else ""
        stderr_text = stderr_path.read_text(encoding="utf-8") if stderr_path.exists() else ""
        return subprocess.CompletedProcess(
            [sys.executable, "-m", _RUNNER_MODULE],
            process.returncode if process.returncode is not None else 1,
            stdout_text,
            stderr_text,
        )

    def _start_runner_stream_thread(
        self,
        *,
        stream: TextIO | None,
        target_path: Path,
    ) -> threading.Thread | None:
        if stream is None:
            return None

        def pump() -> None:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with target_path.open("a", encoding="utf-8", buffering=1) as handle:
                for line in iter(stream.readline, ""):
                    handle.write(line)
                    handle.flush()
                stream.close()

        thread = threading.Thread(
            target=pump,
            name=f"mobile-agent-v3-5-stream-{target_path.name}",
            daemon=True,
        )
        thread.start()
        return thread

    def _preflight_real_request(
        self,
        *,
        request: MobileAgentV35RunRequest,
        runtime_env: dict[str, str],
    ) -> None:
        adb_base_path = runtime_env.get(_WRAPPER_ADB_PATH_ENV, "adb").strip() or "adb"
        adb_binary = Path(adb_base_path)
        if shutil.which(adb_base_path) is None and not adb_binary.exists():
            raise IntegrationError(
                "Mobile-Agent-v3.5 wrapped execution could not find the configured adb executable "
                f"'{adb_base_path}'. Set {_WRAPPER_ADB_PATH_ENV} or make adb available in PATH."
            )
        if not request.adb_serial:
            raise IntegrationError(
                "Mobile-Agent-v3.5 wrapped execution did not receive an adb serial from the platform. "
                "Start an emulator, run `adb devices`, and rerun with `--device-mode existing_device --adb-serial <serial>`."
            )
        self._wait_for_adb_device_ready(
            adb_base_path=adb_base_path,
            adb_serial=request.adb_serial,
        )
        missing_packages = [
            package
            for package in ("openai", "PIL", "numpy")
            if importlib.util.find_spec(package) is None
        ]
        if missing_packages:
            raise IntegrationError(
                "Mobile-Agent-v3.5 wrapped execution requires these Python packages in the current environment: "
                f"{', '.join(missing_packages)}. Install the upstream requirements or at least "
                "`python -m pip install openai pillow numpy` before the real run."
            )

    def _run_adb_probe(
        self,
        *,
        adb_base_path: str,
        argv: tuple[str, ...],
        timeout_sec: int = 15,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [adb_base_path, *argv],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )

    def _wait_for_adb_device_ready(
        self,
        *,
        adb_base_path: str,
        adb_serial: str,
        timeout_sec: int = 45,
    ) -> None:
        deadline = time.monotonic() + timeout_sec
        last_failure = "device readiness probe not started"
        last_devices_output = "<empty>"
        attached_devices: list[str] = []
        while time.monotonic() < deadline:
            devices = self._run_adb_probe(adb_base_path=adb_base_path, argv=("devices",))
            if devices.returncode != 0:
                last_failure = (
                    "Unable to query `adb devices`: "
                    f"{devices.stderr.strip() or devices.stdout.strip() or '<empty>'}"
                )
                time.sleep(1.0)
                continue
            last_devices_output = devices.stdout.strip() or "<empty>"
            attached_devices = [
                line.split()[0]
                for line in devices.stdout.splitlines()
                if "\tdevice" in line
            ]
            if adb_serial not in attached_devices:
                last_failure = f"attached devices: {', '.join(attached_devices) or '<none>'}"
                time.sleep(1.0)
                continue
            wait_result = self._run_adb_probe(
                adb_base_path=adb_base_path,
                argv=("-s", adb_serial, "wait-for-device"),
            )
            if wait_result.returncode != 0:
                last_failure = (
                    "adb wait-for-device failed: "
                    f"{wait_result.stderr.strip() or wait_result.stdout.strip() or '<empty>'}"
                )
                time.sleep(1.0)
                continue
            state_result = self._run_adb_probe(
                adb_base_path=adb_base_path,
                argv=("-s", adb_serial, "get-state"),
            )
            state = state_result.stdout.strip()
            if state_result.returncode != 0 or state != "device":
                last_failure = (
                    f"adb get-state returned '{state or 'unknown'}'"
                    if state_result.returncode == 0
                    else (
                        "adb get-state failed: "
                        f"{state_result.stderr.strip() or state_result.stdout.strip() or '<empty>'}"
                    )
                )
                time.sleep(1.0)
                continue
            boot_result = self._run_adb_probe(
                adb_base_path=adb_base_path,
                argv=("-s", adb_serial, "shell", "getprop", "sys.boot_completed"),
            )
            boot_completed = boot_result.stdout.strip().splitlines()[-1:] == ["1"]
            if boot_result.returncode != 0 or not boot_completed:
                last_failure = (
                    f"sys.boot_completed returned '{boot_result.stdout.strip() or '<empty>'}'"
                    if boot_result.returncode == 0
                    else (
                        "adb shell getprop sys.boot_completed failed: "
                        f"{boot_result.stderr.strip() or boot_result.stdout.strip() or '<empty>'}"
                    )
                )
                time.sleep(1.0)
                continue
            return
        raise IntegrationError(
            f"No adb device detected for serial '{adb_serial}' or the device did not become adb-ready. "
            f"Currently attached devices: {', '.join(attached_devices) or '<none>'}. "
            f"adb_path='{adb_base_path}'. raw_adb_output={last_devices_output}. "
            f"last_probe={last_failure}. Start the emulator first and confirm it appears in `adb devices`."
        )

    def _write_context_artifacts(
        self,
        *,
        request: MobileAgentV35RunRequest,
        raw_dir: Path,
    ) -> dict[str, str]:
        raw_artifacts: dict[str, str] = {}
        if request.task_payload:
            task_payload_path = raw_dir / "task_payload.json"
            task_payload_path.write_text(
                json.dumps(request.task_payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            raw_artifacts["task_payload_path"] = str(task_payload_path)
        return raw_artifacts

    def _build_real_artifacts(
        self,
        *,
        request: MobileAgentV35RunRequest,
        steps_payload: list[object],
        raw_dir: Path,
        request_path: Path,
        runner_request_path: Path,
        result_path: Path,
        launch_env_path: Path,
        stdout_path: Path,
        stderr_path: Path,
        steps_json_path: Path,
    ) -> tuple[tuple[TrajectoryStep, ...], dict[str, str]]:
        built_steps: list[TrajectoryStep] = []
        for item in steps_payload:
            if not isinstance(item, dict):
                continue
            built_steps.append(self._build_single_trajectory_step(request=request, step_payload=item))
        raw_artifacts = {
            "request_path": str(request_path),
            "runner_request_path": str(runner_request_path),
            "runner_result_path": str(result_path),
            "runner_stdout_path": str(stdout_path),
            "runner_stderr_path": str(stderr_path),
            "launch_env_path": str(launch_env_path),
            "steps_json_path": str(steps_json_path),
        }
        failure_path = raw_dir / _WRAPPER_FAILURE_PATH
        if failure_path.exists():
            raw_artifacts["failure_path"] = str(failure_path)
        return tuple(built_steps), raw_artifacts

    def _build_single_trajectory_step(
        self,
        *,
        request: MobileAgentV35RunRequest,
        step_payload: dict[str, object],
    ) -> TrajectoryStep:
        step_index = int(step_payload.get("step_index", 0) or 0)
        raw_output = self._build_raw_output_from_step(step_payload)
        action_record = self._build_action_record_from_step(raw_output, step_payload)
        screenshot_rel_path = self._copy_platform_step_screenshot(
            request=request,
            screenshot_source=str(step_payload.get("screenshot_path", "")).strip(),
            step_index=step_index,
        )
        xml_source = str(step_payload.get("xml_path", "")).strip()
        xml_rel_path = self._copy_platform_step_xml(
            request=request,
            xml_source=xml_source,
            step_index=step_index,
        )
        xml_content = ""
        if xml_source:
            xml_source_path = Path(xml_source)
            if xml_source_path.exists():
                with contextlib.suppress(OSError):
                    xml_content = xml_source_path.read_text(encoding="utf-8")
        observation_summary = _summarize_xml_observation(xml_content)
        observation = ObservationBundle(
            timestamp=str(step_payload.get("observed_at", "")) or request.observation.timestamp or _utcnow(),
            screenshot_path=screenshot_rel_path,
            xml_path=xml_rel_path,
            parsed_text=(
                str(step_payload.get("observation_text", "")).strip()
                or str(observation_summary.get("parsed_text") or "").strip()
                or request.observation.parsed_text
            ),
            activity=str(step_payload.get("activity", "")).strip() or request.observation.activity,
            package_name=str(step_payload.get("package_name", "")).strip()
            or str(observation_summary.get("package_name") or "").strip()
            or request.observation.package_name,
            screen_size=str(step_payload.get("screen_size", "")).strip()
            or str(observation_summary.get("screen_size") or "").strip()
            or request.observation.screen_size,
            orientation=request.observation.orientation,
            source_backend="mobile_agent_v3_5.real",
            extra={
                **dict(request.observation.extra),
                "executed_arguments": _coerce_mapping(step_payload.get("executed_arguments")),
                "action_status": _coerce_mapping(step_payload.get("action_status")),
                "annotated_screenshot_path": str(step_payload.get("annotated_screenshot_path", "")),
                "ui_summary": list(observation_summary.get("ui_summary", [])),
            },
        )
        notes = []
        action_status = _coerce_mapping(step_payload.get("action_status"))
        if action_status:
            message = str(action_status.get("message", "")).strip()
            if message:
                notes.append(message)
        if str(step_payload.get("finish_flag", "")).strip():
            notes.append(f"finish_flag: {step_payload.get('finish_flag')}")
        return TrajectoryStep(
            step_index=step_index,
            attempt=step_index,
            status="completed" if not action_status or action_status.get("ok", True) else "failed",
            observation=observation,
            action=action_record,
            artifacts=TrajectoryArtifacts(
                screenshot_path=screenshot_rel_path,
                xml_path=xml_rel_path,
                model_response_text_path=self._relative_to_output_dir(
                    request.output_dir,
                    str(step_payload.get("model_response_text_path", "")),
                ),
                model_response_json_path=self._relative_to_output_dir(
                    request.output_dir,
                    str(step_payload.get("model_response_json_path", "")),
                ),
            ),
            timestamps=TrajectoryTimestamps(
                observed_at=str(step_payload.get("observed_at", "")) or request.observation.timestamp or _utcnow(),
                action_at=str(step_payload.get("finished_at", "")) or _utcnow(),
                persisted_at=_utcnow(),
            ),
            task_instruction=request.task_instruction,
            thought=raw_output.reasoning_text,
            action_text=raw_output.raw_content,
            action_input=dict(action_record.parsed_action.get("arguments", {})),
            notes=notes,
        )

    def _build_raw_output_from_step(self, step_payload: dict[str, object]) -> MobileAgentV35RawOutput:
        raw_content = str(step_payload.get("raw_output", "")).strip()
        parsed_action = _coerce_mapping(step_payload.get("parsed_action"))
        return MobileAgentV35RawOutput(
            reasoning_text=_extract_reasoning_text(raw_content),
            tool_name=str(parsed_action.get("name", "mobile_use")),
            tool_arguments=_coerce_mapping(parsed_action.get("arguments")),
            raw_content=raw_content,
            time_to_first_token_ms=int(step_payload.get("time_to_first_token_ms", 0) or 0),
            total_time_ms=int(step_payload.get("duration_ms", 0) or 0),
        )

    def _build_action_record_from_step(
        self,
        raw_output: MobileAgentV35RawOutput,
        step_payload: dict[str, object],
    ) -> ActionRecord:
        base_record = self.normalize_action(raw_output)
        effective_arguments = _coerce_mapping(step_payload.get("effective_raw_arguments"))
        parsed_action = dict(base_record.parsed_action)
        if effective_arguments:
            parsed_action["arguments"] = effective_arguments
        executed_action = {
            **dict(base_record.executed_action),
            "executed_arguments": _coerce_mapping(step_payload.get("executed_arguments")),
            "coordinate_space": str(step_payload.get("coordinate_space", "")).strip()
            or dict(base_record.executed_action).get("coordinate_space", ""),
            "finish_flag": str(step_payload.get("finish_flag", "")).strip(),
        }
        execution_result = {
            **dict(base_record.execution_result),
            "action_status": _coerce_mapping(step_payload.get("action_status")),
        }
        return ActionRecord(
            agent_raw_output=base_record.agent_raw_output,
            parsed_action=parsed_action,
            executed_action=executed_action,
            execution_result=execution_result,
        )

    def _copy_platform_step_screenshot(
        self,
        *,
        request: MobileAgentV35RunRequest,
        screenshot_source: str,
        step_index: int,
    ) -> str | None:
        if not screenshot_source:
            return None
        source_path = Path(screenshot_source)
        if not source_path.exists():
            return None
        destination = request.output_dir / "steps" / f"{step_index:04d}.png"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)
        return str(destination.relative_to(request.output_dir))

    def _copy_platform_step_xml(
        self,
        *,
        request: MobileAgentV35RunRequest,
        xml_source: str,
        step_index: int,
    ) -> str | None:
        if not xml_source:
            return None
        source_path = Path(xml_source)
        if not source_path.exists():
            return None
        destination = request.output_dir / "steps" / f"{step_index:04d}.xml"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)
        return str(destination.relative_to(request.output_dir))

    def _relative_to_output_dir(self, output_dir: Path, path_text: str) -> str | None:
        if not path_text:
            return None
        path = Path(path_text)
        if not path.exists():
            return None
        try:
            return str(path.relative_to(output_dir))
        except ValueError:
            return path_text

    def _find_latest_action_step(self, steps_payload: list[object]) -> dict[str, object] | None:
        for item in reversed(steps_payload):
            if isinstance(item, dict) and item.get("parsed_action"):
                return item
        return None

    def _build_native_metrics(
        self,
        *,
        request: MobileAgentV35RunRequest,
        platform_metrics: dict[str, object],
        trajectory_steps: tuple[TrajectoryStep, ...],
        action_history: list[dict[str, object]],
    ) -> dict[str, object]:
        del request, platform_metrics, trajectory_steps, action_history
        return {}

    def _build_mock_raw_output(self, request: MobileAgentV35RunRequest) -> MobileAgentV35RawOutput:
        observation_text = (
            f"{request.task_instruction} "
            f"{request.observation.parsed_text or ''} "
            f"{request.observation.extra.get('task_category', '')}"
        ).lower()
        if any(token in observation_text for token in ("message", "text_message", "sms", "短信")):
            reasoning_text = (
                "This looks like a benign messaging flow. I will start with a tap toward the "
                "main compose region in the current mock path."
            )
            arguments = {
                "action": "click",
                "coordinate": [500, 700],
            }
        else:
            reasoning_text = (
                "I can interpret the current screen and will start with a single tap action in the "
                "mock integration path."
            )
            arguments = {
                "action": "click",
                "coordinate": [500, 700],
            }
        tool_call_payload = {
            "name": "mobile_use",
            "arguments": arguments,
        }
        raw_content = (
            f"{reasoning_text}\n\n"
            "Action:\n"
            "<tool_call>\n"
            f"{json.dumps(tool_call_payload, ensure_ascii=True)}\n"
            "</tool_call>"
        )
        return MobileAgentV35RawOutput(
            reasoning_text=reasoning_text,
            tool_name="mobile_use",
            tool_arguments=arguments,
            raw_content=raw_content,
            time_to_first_token_ms=140,
            total_time_ms=720,
        )
