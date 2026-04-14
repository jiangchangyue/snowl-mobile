from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from snowl_mobile.adapters.agents.base import WrappedAgentAdapter
from snowl_mobile.adapters.base import AdapterMetadata
from snowl_mobile.core.agent_spec import AgentSpec
from snowl_mobile.core.enums import IntegrationMode, WorkerMode
from snowl_mobile.core.errors import IntegrationError, PhaseStubError
from snowl_mobile.core.trial_context import TrialContext
from snowl_mobile.integration.agent_contract import (
    AgentAdapterContract,
    AgentCapabilityDeclaration,
    AgentContractValidator,
)
from snowl_mobile.integration.references import resolve_repo_under_references
from snowl_mobile.schemas.action import ActionRecord
from snowl_mobile.schemas.observation import ObservationBundle


_REPO_ENV_VAR = "OPEN_AUTOGLM_HOME"
_DEFAULT_REPO_CANDIDATES = (
    Path("references/agents/Open-AutoGLM"),
    Path("references/agents/open-autoglm"),
)
_REQUIRED_REPO_MARKERS = (
    Path("README.md"),
    Path("main.py"),
    Path("phone_agent/agent.py"),
    Path("phone_agent/model/client.py"),
    Path("phone_agent/actions/handler.py"),
)


@dataclass(frozen=True, slots=True)
class OpenAutoGLMModelBindingDeclaration:
    api_style: str
    modalities: tuple[str, ...]
    supports_image_input: bool
    supports_tool_calling: bool
    supports_json_mode: bool
    base_url_env: str
    api_key_env: str
    default_model_name: str
    compatible_provider_examples: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "api_style": self.api_style,
            "modalities": list(self.modalities),
            "supports_image_input": self.supports_image_input,
            "supports_tool_calling": self.supports_tool_calling,
            "supports_json_mode": self.supports_json_mode,
            "base_url_env": self.base_url_env,
            "api_key_env": self.api_key_env,
            "default_model_name": self.default_model_name,
            "compatible_provider_examples": list(self.compatible_provider_examples),
        }


@dataclass(frozen=True, slots=True)
class OpenAutoGLMRepositoryReport:
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
class OpenAutoGLMRawOutput:
    thinking: str
    action_text: str
    raw_content: str
    time_to_first_token_ms: int
    time_to_thinking_end_ms: int
    total_time_ms: int

    def to_dict(self) -> dict[str, object]:
        return {
            "thinking": self.thinking,
            "action_text": self.action_text,
            "raw_content": self.raw_content,
            "time_to_first_token_ms": self.time_to_first_token_ms,
            "time_to_thinking_end_ms": self.time_to_thinking_end_ms,
            "total_time_ms": self.total_time_ms,
        }


@dataclass(frozen=True, slots=True)
class OpenAutoGLMRunRequest:
    repo_path: Path
    output_dir: Path
    model_id: str
    task_instruction: str
    observation: ObservationBundle
    control_backend: str
    max_steps: int
    mock_mode: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "repo_path": self.repo_path.as_posix(),
            "output_dir": self.output_dir.as_posix(),
            "model_id": self.model_id,
            "task_instruction": self.task_instruction,
            "control_backend": self.control_backend,
            "max_steps": self.max_steps,
            "mock_mode": self.mock_mode,
            "observation": {
                "timestamp": self.observation.timestamp,
                "screenshot_path": self.observation.screenshot_path,
                "xml_path": self.observation.xml_path,
                "parsed_text": self.observation.parsed_text,
                "source_backend": self.observation.source_backend,
                "extra": dict(self.observation.extra),
            },
        }


@dataclass(frozen=True, slots=True)
class OpenAutoGLMRunResult:
    request: OpenAutoGLMRunRequest
    raw_output: OpenAutoGLMRawOutput
    action_record: ActionRecord
    raw_artifacts: dict[str, str]
    platform_metrics: dict[str, object]
    model_binding: OpenAutoGLMModelBindingDeclaration

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
        }


def resolve_open_autoglm_repo_path(repo_path: Path | None = None) -> Path:
    return resolve_repo_under_references(
        integration_name="Open-AutoGLM repository",
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


def build_open_autoglm_model_binding() -> OpenAutoGLMModelBindingDeclaration:
    return OpenAutoGLMModelBindingDeclaration(
        api_style="openai_chat",
        modalities=("text", "image"),
        supports_image_input=True,
        supports_tool_calling=False,
        supports_json_mode=False,
        base_url_env="PHONE_AGENT_BASE_URL",
        api_key_env="PHONE_AGENT_API_KEY",
        default_model_name="autoglm-phone-9b",
        compatible_provider_examples=(
            "local_openai_compatible_server",
            "bigmodel_autoglm_phone",
            "modelscope_autoglm_phone",
        ),
    )


def build_open_autoglm_contract() -> AgentAdapterContract:
    return AgentContractValidator().validate(
        AgentAdapterContract(
            observation_transform_entry="phone_agent/agent.py::PhoneAgent._execute_step",
            step_entry="phone_agent/agent.py::PhoneAgent.step",
            run_entry="main.py::main",
            action_normalization_entry="phone_agent/actions/handler.py::parse_action",
            model_call_entry="phone_agent/model/client.py::ModelClient.request",
            device_control_entry="phone_agent/device_factory.py::DeviceFactory",
            raw_output_capture_points=(
                "phone_agent/model/client.py::ModelResponse.raw_content",
                "phone_agent/agent.py::PhoneAgent.context",
                "stdout(thinking/action transcript)",
            ),
            capability=AgentCapabilityDeclaration(
                input_modalities=("text", "image"),
                action_output_schema="autoglm_pseudocode_v1",
                supported_model_protocols=("openai_chat",),
                tool_backends=("adb_appium", "adb", "hdc", "ios_wda"),
                runtime_requirements=("pillow", "openai", "requests"),
                human_confirmation_mode="confirmation_callback+takeover_callback",
                raw_output_capture_points=(
                    "phone_agent/model/client.py::ModelResponse.raw_content",
                    "phone_agent/agent.py::PhoneAgent.context",
                    "stdout(thinking/action transcript)",
                ),
                supports_image_input=True,
                supports_tool_calling=False,
                supports_json_mode=False,
                requires_tool_calling=False,
                requires_json_mode=False,
            ),
        )
    )


def build_open_autoglm_report(repo_path: Path | None = None) -> OpenAutoGLMRepositoryReport:
    resolved = resolve_open_autoglm_repo_path(repo_path)
    return OpenAutoGLMRepositoryReport(
        repo_path=resolved,
        observation_entry="phone_agent/agent.py::PhoneAgent._execute_step",
        run_entry="main.py::main",
        model_call_entry="phone_agent/model/client.py::ModelClient.request",
        action_generation_entry="phone_agent/config/prompts*.py + phone_agent/model/client.py::_parse_response",
        action_normalization_entry="phone_agent/actions/handler.py::parse_action",
        device_control_entry="phone_agent/device_factory.py::DeviceFactory",
        observation_modalities=("text", "image"),
        action_output_form='single-line pseudo-code: do(action="...") / finish(message="...")',
        model_dependency_mode="OpenAI-compatible vision-language endpoint via base_url + model_name + api_key",
        device_control_backends=("adb", "hdc", "ios_wda"),
        raw_output_capture_points=(
            "phone_agent/model/client.py::ModelResponse.raw_content",
            "phone_agent/agent.py::PhoneAgent.context",
            "console verbose transcript",
        ),
        recommended_integration_mode=IntegrationMode.HYBRID.value,
        rationale=(
            "Open-AutoGLM exposes a reusable Python package surface (`phone_agent/*`) for prompts, model calls, action parsing, and device control.",
            "Its top-level UX is still centered on `main.py` and interactive device-side execution, so a pure native refactor would be premature for the first integration.",
            "A wrap-first hybrid adapter keeps model/action contracts explicit while leaving real device execution to a later runtime-wiring phase.",
        ),
    )


def _extract_action_text(raw_content: str) -> str:
    return _sanitize_open_autoglm_action_text(raw_content)


def _sanitize_open_autoglm_action_text(response: str) -> str:
    content = response.strip()
    for fence in ("```python", "```json", "```text", "```"):
        content = content.replace(fence, "")
    if "<answer>" in content:
        content = content.split("<answer>", 1)[1]
    if "</answer>" in content:
        content = content.split("</answer>", 1)[0]
    if "finish(message=" in content:
        content = "finish(message=" + content.split("finish(message=", 1)[1]
    elif "do(action=" in content:
        content = "do(action=" + content.split("do(action=", 1)[1]
    return content.strip()


def parse_open_autoglm_action_text(response: str) -> dict[str, Any]:
    response = _sanitize_open_autoglm_action_text(response)
    if response.startswith('do(action="Type"') or response.startswith('do(action="Type_Name"'):
        text = response.split("text=", 1)[1][1:-2]
        return {"_metadata": "do", "action": "Type", "text": text}
    if response.startswith("do"):
        sanitized = response.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        tree = ast.parse(sanitized, mode="eval")
        if not isinstance(tree.body, ast.Call):
            raise IntegrationError("Open-AutoGLM action parser expected a function call")
        parsed: dict[str, Any] = {"_metadata": "do"}
        for keyword in tree.body.keywords:
            if keyword.arg is None:
                raise IntegrationError("Open-AutoGLM action parser does not support **kwargs expansion")
            parsed[keyword.arg] = ast.literal_eval(keyword.value)
        return parsed
    if response.startswith("finish"):
        return {
            "_metadata": "finish",
            "message": response.replace("finish(message=", "")[1:-2],
        }
    raise IntegrationError(f"Unsupported Open-AutoGLM action response: {response}")


def _normalize_parsed_action(parsed_action: dict[str, Any]) -> dict[str, Any]:
    kind = str(parsed_action.get("_metadata", "unknown"))
    action_name = str(parsed_action.get("action", "finish" if kind == "finish" else "unknown"))
    normalized_name = {
        "Launch": "launch_app",
        "Tap": "tap",
        "Type": "type_text",
        "Swipe": "swipe",
        "Back": "back",
        "Home": "home",
        "Double Tap": "double_tap",
        "Long Press": "long_press",
        "Wait": "wait",
        "Take_over": "manual_takeover",
        "Interact": "manual_interaction",
        "Note": "note",
        "Call_API": "call_api",
    }.get(action_name, action_name.lower().replace(" ", "_"))
    arguments = {
        key: value
        for key, value in parsed_action.items()
        if key not in {"_metadata", "action"}
    }
    coordinate_fields = [
        key for key in ("element", "start", "end") if key in arguments
    ]
    requires_confirmation = bool(
        kind == "do"
        and action_name in {"Tap", "Launch", "Type", "Long Press", "Double Tap"}
        and "message" in arguments
    )
    requires_human_takeover = action_name in {"Take_over", "Interact"}
    return {
        "schema": "autoglm_phone_action_v1",
        "kind": kind,
        "action_name": action_name,
        "normalized_action": normalized_name,
        "arguments": arguments,
        "coordinate_space": "relative_0_1000" if coordinate_fields else "",
        "coordinate_fields": coordinate_fields,
        "requires_confirmation": requires_confirmation,
        "requires_human_takeover": requires_human_takeover,
    }


class OpenAutoGLMAgentAdapter(WrappedAgentAdapter):
    @property
    def adapter_id(self) -> str:
        return "open_autoglm"

    def describe(self) -> AgentSpec:
        return AgentSpec(
            agent_id=self.adapter_id,
            display_name="Open-AutoGLM",
            variant="default",
            model_ref="autoglm_phone_api",
            integration_mode=IntegrationMode.HYBRID,
            required_modalities=("text", "image"),
            supported_modalities=("text", "image"),
            supported_backends=("adb_appium", "adb", "hdc", "ios_wda"),
            supported_model_protocols=("openai_chat",),
            supports_tool_calling=False,
            supports_image_input=True,
            supports_json_mode=False,
            requires_tool_calling=False,
            requires_json_mode=False,
            required_env=(_REPO_ENV_VAR,),
            action_schema="autoglm_phone_action_v1",
            prompt_contract_version="open-autoglm.v1",
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
            },
        )

    def transform_observation(self, observation: ObservationBundle) -> ObservationBundle:
        extra = dict(observation.extra)
        extra.setdefault("upstream_observation_entry", self.contract().observation_transform_entry)
        extra.setdefault("expected_modalities", list(self.describe().required_modalities))
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
            source_backend=observation.source_backend or "open_autoglm.wrap",
            extra=extra,
        )

    def normalize_action(self, raw_output: object) -> ActionRecord:
        structured = self._coerce_raw_output(raw_output)
        parsed_action = parse_open_autoglm_action_text(structured.action_text)
        normalized_action = _normalize_parsed_action(parsed_action)
        return ActionRecord(
            agent_raw_output=structured.raw_content,
            parsed_action=parsed_action,
            executed_action=normalized_action,
            execution_result={
                "thinking": structured.thinking,
                "time_to_first_token_ms": structured.time_to_first_token_ms,
                "time_to_thinking_end_ms": structured.time_to_thinking_end_ms,
                "total_time_ms": structured.total_time_ms,
            },
        )

    def capture_raw_output(self, raw_output: object) -> dict[str, str]:
        structured = self._coerce_raw_output(raw_output)
        return {
            "thinking": structured.thinking,
            "action_text": structured.action_text,
            "raw_content": structured.raw_content,
            "time_to_first_token_ms": str(structured.time_to_first_token_ms),
            "time_to_thinking_end_ms": str(structured.time_to_thinking_end_ms),
            "total_time_ms": str(structured.total_time_ms),
        }

    def repository_report(self) -> OpenAutoGLMRepositoryReport:
        return build_open_autoglm_report()

    def contract(self) -> AgentAdapterContract:
        return build_open_autoglm_contract()

    def model_binding_declaration(self) -> OpenAutoGLMModelBindingDeclaration:
        return build_open_autoglm_model_binding()

    def build_run_request(
        self,
        ctx: TrialContext,
        *,
        output_dir: Path,
        observation: ObservationBundle,
        task_instruction: str,
        mock_mode: bool = True,
    ) -> OpenAutoGLMRunRequest:
        return OpenAutoGLMRunRequest(
            repo_path=resolve_open_autoglm_repo_path(),
            output_dir=output_dir,
            model_id=ctx.trial_spec.model_id,
            task_instruction=task_instruction,
            observation=self.transform_observation(observation),
            control_backend=ctx.trial_spec.runtime_recipe.control_backend,
            max_steps=ctx.trial_spec.max_steps,
            mock_mode=mock_mode,
        )

    def run_wrapped_agent(self, request: OpenAutoGLMRunRequest) -> OpenAutoGLMRunResult:
        if not request.mock_mode:
            raise PhaseStubError(
                "Real Open-AutoGLM wrapped execution is intentionally deferred until a later "
                "phase wires emulator leases, model credentials, and device backends into the orchestrator."
            )
        return self._run_mock_request(request)

    def _coerce_raw_output(self, raw_output: object) -> OpenAutoGLMRawOutput:
        if isinstance(raw_output, OpenAutoGLMRawOutput):
            return raw_output
        if isinstance(raw_output, str):
            action_text = _extract_action_text(raw_output)
            return OpenAutoGLMRawOutput(
                thinking=raw_output.replace(action_text, "").strip(),
                action_text=action_text,
                raw_content=raw_output,
                time_to_first_token_ms=0,
                time_to_thinking_end_ms=0,
                total_time_ms=0,
            )
        raise IntegrationError(
            f"Unsupported Open-AutoGLM raw output type: {type(raw_output).__name__}"
        )

    def _run_mock_request(self, request: OpenAutoGLMRunRequest) -> OpenAutoGLMRunResult:
        raw_dir = request.output_dir / "raw" / "open_autoglm"
        raw_dir.mkdir(parents=True, exist_ok=True)

        raw_output = self._build_mock_raw_output(request)
        action_record = self.normalize_action(raw_output)
        raw_capture = self.capture_raw_output(raw_output)

        request_path = raw_dir / "request.json"
        observation_path = raw_dir / "observation.json"
        raw_text_path = raw_dir / "model_response.txt"
        raw_json_path = raw_dir / "model_response.json"
        action_path = raw_dir / "action_record.json"
        binding_path = raw_dir / "model_binding.json"
        result_path = raw_dir / "wrapped_result.json"

        request_path.write_text(
            json.dumps(request.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
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

        platform_metrics = {
            "step_count": 1,
            "finished": action_record.parsed_action.get("_metadata") == "finish",
            "requires_confirmation": bool(action_record.executed_action.get("requires_confirmation")),
            "requires_human_takeover": bool(
                action_record.executed_action.get("requires_human_takeover")
            ),
            "control_backend": request.control_backend,
            "total_time_ms": raw_output.total_time_ms,
            "mock_mode": True,
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
        }
        return OpenAutoGLMRunResult(
            request=request,
            raw_output=raw_output,
            action_record=action_record,
            raw_artifacts=raw_artifacts,
            platform_metrics=platform_metrics,
            model_binding=self.model_binding_declaration(),
        )

    def _build_mock_raw_output(self, request: OpenAutoGLMRunRequest) -> OpenAutoGLMRawOutput:
        observation_text = (
            f"{request.task_instruction} "
            f"{request.observation.parsed_text or ''} "
            f"{request.observation.extra.get('task_category', '')}"
        ).lower()
        if any(token in observation_text for token in ("message", "text_message", "短信")):
            thinking = (
                "This looks like a messaging task. In the current mock integration path, I will "
                "start with a single tap before continuing."
            )
            action_text = 'do(action="Tap", element=[512,820])'
        else:
            thinking = (
                "I can see the current screen and will start with a single navigation step before "
                "continuing the task."
            )
            action_text = 'do(action="Tap", element=[512,820])'
        raw_content = f"{thinking}\n{action_text}"
        return OpenAutoGLMRawOutput(
            thinking=thinking,
            action_text=action_text,
            raw_content=raw_content,
            time_to_first_token_ms=120,
            time_to_thinking_end_ms=360,
            total_time_ms=640,
        )
