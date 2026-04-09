from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from snowl_mobile.integration.agent_contract import (
    AgentAdapterContract,
    AgentCapabilityDeclaration,
    AgentContractValidator,
)
from snowl_mobile.integration.repo_inspector import RepositoryInspection, RepositoryInspector


@dataclass(frozen=True, slots=True)
class AgentRepositoryInspection:
    base: RepositoryInspection
    examples_dirs: tuple[str, ...]
    model_entrypoints: tuple[str, ...]
    device_control_candidates: tuple[str, ...]
    action_normalization_candidates: tuple[str, ...]
    observation_modalities: tuple[str, ...]
    action_output_forms: tuple[str, ...]
    tool_backends: tuple[str, ...]
    runtime_requirements: tuple[str, ...]
    human_confirmation_candidates: tuple[str, ...]
    raw_output_capture_points: tuple[str, ...]

    @property
    def repo_name(self) -> str:
        return self.base.repo_name

    @property
    def repo_path(self) -> Path:
        return self.base.repo_path

    @property
    def suggested_integration_mode(self) -> str:
        return self.base.suggested_integration_mode

    @property
    def dependency_hints(self) -> tuple[str, ...]:
        return self.base.dependency_hints

    @property
    def summary_excerpt(self) -> str:
        return self.base.summary_excerpt

    def to_dict(self) -> dict[str, object]:
        payload = self.base.to_dict()
        payload.update(
            {
                "examples_dirs": list(self.examples_dirs),
                "model_entrypoints": list(self.model_entrypoints),
                "device_control_candidates": list(self.device_control_candidates),
                "action_normalization_candidates": list(self.action_normalization_candidates),
                "observation_modalities": list(self.observation_modalities),
                "action_output_forms": list(self.action_output_forms),
                "tool_backends": list(self.tool_backends),
                "runtime_requirements": list(self.runtime_requirements),
                "human_confirmation_candidates": list(self.human_confirmation_candidates),
                "raw_output_capture_points": list(self.raw_output_capture_points),
            }
        )
        return payload

    def default_contract(self, *, capability_profile: str = "auto") -> AgentAdapterContract:
        capability = self.default_capability(capability_profile=capability_profile)
        contract = AgentAdapterContract(
            observation_transform_entry=self._best_candidate(
                self.base.entrypoints + self.device_control_candidates,
                "TODO_observation_transform_entry",
            ),
            step_entry=self._best_candidate(
                self.base.entrypoints,
                "TODO_step_entry",
            ),
            run_entry=self._best_candidate(
                self.base.entrypoints,
                "TODO_run_entry",
            ),
            action_normalization_entry=self._best_candidate(
                self._collect_action_normalization_candidates(),
                "TODO_action_normalization_entry",
            ),
            model_call_entry=self._best_candidate(
                self.model_entrypoints,
                "TODO_model_call_entry",
            ),
            device_control_entry=self._best_candidate(
                self.device_control_candidates,
                "TODO_device_control_entry",
            ),
            raw_output_capture_points=self.raw_output_capture_points or ("TODO_raw_output_capture_point",),
            capability=capability,
        )
        return AgentContractValidator().validate(contract)

    def default_capability(self, *, capability_profile: str = "auto") -> AgentCapabilityDeclaration:
        resolved_profile = capability_profile.lower()
        if resolved_profile not in {"auto", "text-only", "vision-capable"}:
            resolved_profile = "auto"

        if resolved_profile == "text-only":
            modalities = ("text",)
        elif resolved_profile == "vision-capable":
            modalities = ("text", "image")
        else:
            modalities = self.observation_modalities if self.observation_modalities else ("text",)

        action_schema = self._best_candidate(self.action_output_forms, "TODO_action_schema")
        capability = AgentCapabilityDeclaration(
            input_modalities=modalities,
            action_output_schema=action_schema,
            supported_model_protocols=("openai_chat",),
            tool_backends=self.tool_backends or ("adb",),
            runtime_requirements=self.runtime_requirements,
            human_confirmation_mode=self._best_candidate(
                self.human_confirmation_candidates,
                "none",
            ),
            raw_output_capture_points=self.raw_output_capture_points or ("TODO_raw_output_capture_point",),
            supports_image_input="image" in modalities,
            supports_tool_calling=False,
            supports_json_mode="json" in action_schema or "tool" in action_schema,
            requires_tool_calling=False,
            requires_json_mode=False,
        )
        return AgentContractValidator().validate_capability(capability)

    def _best_candidate(self, values: tuple[str, ...], fallback: str) -> str:
        if not values:
            return fallback
        for value in values:
            if "/" in value or "." in Path(value).name:
                return value
        return values[0]

    def _collect_action_normalization_candidates(self) -> tuple[str, ...]:
        candidates = tuple(
            value
            for value in (
                *self.action_normalization_candidates,
                *self.base.entrypoints,
                *self.raw_output_capture_points,
            )
            if "action" in value.lower() or "parser" in value.lower() or "output" in value.lower()
        )
        return candidates


class AgentRepositoryInspector:
    """Richer agent-specific inspection built on top of the generic local repo inspector."""

    def __init__(self, *, base_inspector: RepositoryInspector | None = None) -> None:
        self.base_inspector = base_inspector or RepositoryInspector()

    def inspect(self, repo_path: Path) -> AgentRepositoryInspection:
        base = self.base_inspector.inspect(repo_path, repo_kind="agent")
        resolved = base.repo_path
        examples_dirs = self._collect_dirs(resolved, ("example", "examples", "sample", "samples"))
        model_entrypoints = self._collect_code_candidates(
            resolved,
            keywords=("model", "llm", "client", "openai", "inference", "prompt"),
        )
        device_control_candidates = self._collect_code_candidates(
            resolved,
            keywords=("adb", "appium", "device", "controller", "uiautomator", "backend", "xctest", "hdc"),
        )
        action_normalization_candidates = self._collect_code_candidates(
            resolved,
            keywords=("action", "parser", "normaliz", "executor"),
            content_keywords=("parse_action", "normalize_action", "action_handler"),
        )
        action_output_forms = self._infer_action_output_forms(resolved)
        observation_modalities = self._infer_observation_modalities(resolved, base.dependency_hints)
        tool_backends = self._infer_tool_backends(resolved, base.dependency_hints)
        runtime_requirements = base.dependency_hints
        human_confirmation_candidates = self._collect_code_candidates(
            resolved,
            keywords=("confirm", "approval", "human", "manual", "review"),
            content_keywords=("confirmation_callback", "takeover_callback", "confirm?", "manual operation"),
        )
        raw_output_capture_points = self._collect_code_candidates(
            resolved,
            keywords=("raw", "capture", "trace", "transcript", "log", "output"),
            content_keywords=("raw_content", "traceback", "capture_output", "create_assistant_message"),
        )
        return AgentRepositoryInspection(
            base=base,
            examples_dirs=examples_dirs,
            model_entrypoints=model_entrypoints,
            device_control_candidates=device_control_candidates,
            action_normalization_candidates=action_normalization_candidates,
            observation_modalities=observation_modalities,
            action_output_forms=action_output_forms,
            tool_backends=tool_backends,
            runtime_requirements=runtime_requirements,
            human_confirmation_candidates=human_confirmation_candidates,
            raw_output_capture_points=raw_output_capture_points,
        )

    def _collect_dirs(self, resolved: Path, names: tuple[str, ...]) -> tuple[str, ...]:
        candidates = {
            path.relative_to(resolved).as_posix()
            for path in resolved.rglob("*")
            if path.is_dir() and path.name.lower() in names
        }
        return tuple(sorted(candidates))

    def _collect_code_candidates(
        self,
        resolved: Path,
        *,
        keywords: tuple[str, ...],
        content_keywords: tuple[str, ...] = (),
    ) -> tuple[str, ...]:
        candidates: set[str] = set()
        for path in resolved.rglob("*"):
            if any(part in {".git", ".venv", "__pycache__"} for part in path.parts):
                continue
            if path.is_dir():
                continue
            if path.suffix not in {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml"}:
                continue
            lowered = path.name.lower()
            if any(keyword in lowered for keyword in keywords):
                candidates.add(path.relative_to(resolved).as_posix())
                continue
            if not content_keywords:
                continue
            try:
                text = path.read_text(encoding="utf-8").lower()
            except OSError:
                continue
            if any(keyword in text for keyword in content_keywords):
                candidates.add(path.relative_to(resolved).as_posix())
        return tuple(sorted(candidates))

    def _infer_observation_modalities(
        self,
        resolved: Path,
        dependency_hints: tuple[str, ...],
    ) -> tuple[str, ...]:
        detected = ["text"]
        sample_text = self._sample_text(resolved)
        vision_hints = ("image", "screenshot", "vision", "ui_tree", "xml", "hierarchy")
        if any(token in sample_text for token in vision_hints) or any(
            any(token in dependency for token in ("pillow", "opencv", "torchvision", "uiautomator"))
            for dependency in dependency_hints
        ):
            detected.append("image")
        return tuple(dict.fromkeys(detected))

    def _infer_action_output_forms(self, resolved: Path) -> tuple[str, ...]:
        sample_text = self._sample_text(resolved)
        detected: list[str] = []
        if "json" in sample_text:
            detected.append("json_action")
        if "tool" in sample_text or "function_call" in sample_text:
            detected.append("tool_call")
        if "tap(" in sample_text or "swipe(" in sample_text or "action" in sample_text:
            detected.append("mobile_action")
        if not detected:
            detected.append("text_action")
        return tuple(dict.fromkeys(detected))

    def _infer_tool_backends(
        self,
        resolved: Path,
        dependency_hints: tuple[str, ...],
    ) -> tuple[str, ...]:
        sample_text = self._sample_text(resolved)
        detected: list[str] = []
        if "adb" in sample_text or any("adb" in dependency for dependency in dependency_hints):
            detected.append("adb")
        if "hdc" in sample_text:
            detected.append("hdc")
        if "xctest" in sample_text or "webdriveragent" in sample_text or "ios" in sample_text:
            detected.append("ios_wda")
        if "appium" in sample_text or any("appium" in dependency for dependency in dependency_hints):
            detected.append("appium")
        if "grpc" in sample_text or any("grpc" in dependency for dependency in dependency_hints):
            detected.append("grpc")
        if not detected:
            detected.append("adb")
        return tuple(dict.fromkeys(detected))

    def _sample_text(self, resolved: Path) -> str:
        chunks: list[str] = []
        for path in resolved.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml"}:
                continue
            try:
                chunks.append(path.read_text(encoding="utf-8").lower())
            except OSError:
                continue
            if len(chunks) >= 12:
                break
        return "\n".join(chunks)
