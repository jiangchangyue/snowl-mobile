from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from snowl_mobile.core.enums import IntegrationMode, WorkerMode
from snowl_mobile.core.validation import (
    expect_bool,
    expect_enum_member,
    expect_string,
    expect_string_list,
    get_optional,
    get_required,
)
from snowl_mobile.schemas.base import SchemaModel

if TYPE_CHECKING:
    from snowl_mobile.core.benchmark_spec import BenchmarkSpec
    from snowl_mobile.models.model_spec import ModelSpec


@dataclass(frozen=True, slots=True)
class AgentSpec(SchemaModel):
    agent_id: str
    display_name: str
    variant: str
    model_ref: str
    integration_mode: IntegrationMode
    required_modalities: tuple[str, ...]
    supported_modalities: tuple[str, ...]
    supported_backends: tuple[str, ...]
    supported_model_protocols: tuple[str, ...]
    supports_tool_calling: bool
    supports_image_input: bool
    supports_json_mode: bool
    requires_tool_calling: bool
    requires_json_mode: bool
    required_env: tuple[str, ...]
    action_schema: str
    prompt_contract_version: str
    worker_mode: WorkerMode | None
    supported_benchmarks: tuple[str, ...]

    @classmethod
    def from_mapping(cls, data: dict[str, object], path: str) -> "AgentSpec":
        raw_worker_mode = get_optional(data, "worker_mode", None)
        spec = cls(
            agent_id=expect_string(
                get_required(data, "agent_id", path, aliases=("id",)),
                f"{path}.agent_id",
            ),
            display_name=expect_string(
                get_optional(data, "display_name", get_required(data, "agent_id", path, aliases=("id",))),
                f"{path}.display_name",
            ),
            variant=expect_string(get_optional(data, "variant", "default"), f"{path}.variant"),
            model_ref=expect_string(get_required(data, "model_ref", path), f"{path}.model_ref"),
            integration_mode=expect_enum_member(
                get_optional(data, "integration_mode", IntegrationMode.WRAP.value),
                f"{path}.integration_mode",
                IntegrationMode,
            ),
            required_modalities=expect_string_list(
                get_optional(data, "required_modalities", []),
                f"{path}.required_modalities",
            ),
            supported_modalities=expect_string_list(
                get_optional(data, "supported_modalities", []),
                f"{path}.supported_modalities",
                allow_empty=False,
            ),
            supported_backends=expect_string_list(
                get_optional(data, "supported_backends", []),
                f"{path}.supported_backends",
            ),
            supported_model_protocols=expect_string_list(
                get_optional(data, "supported_model_protocols", []),
                f"{path}.supported_model_protocols",
                allow_empty=False,
            ),
            supports_tool_calling=expect_bool(
                get_optional(data, "supports_tool_calling", False),
                f"{path}.supports_tool_calling",
            ),
            supports_image_input=expect_bool(
                get_optional(data, "supports_image_input", False),
                f"{path}.supports_image_input",
            ),
            supports_json_mode=expect_bool(
                get_optional(data, "supports_json_mode", False),
                f"{path}.supports_json_mode",
            ),
            requires_tool_calling=expect_bool(
                get_optional(data, "requires_tool_calling", False),
                f"{path}.requires_tool_calling",
            ),
            requires_json_mode=expect_bool(
                get_optional(data, "requires_json_mode", False),
                f"{path}.requires_json_mode",
            ),
            required_env=expect_string_list(
                get_optional(data, "required_env", []),
                f"{path}.required_env",
            ),
            action_schema=expect_string(
                get_optional(data, "action_schema", "default_action"),
                f"{path}.action_schema",
            ),
            prompt_contract_version=expect_string(
                get_optional(data, "prompt_contract_version", "v1"),
                f"{path}.prompt_contract_version",
            ),
            worker_mode=None
            if raw_worker_mode is None
            else expect_enum_member(raw_worker_mode, f"{path}.worker_mode", WorkerMode),
            supported_benchmarks=expect_string_list(
                get_optional(data, "supported_benchmarks", []),
                f"{path}.supported_benchmarks",
            ),
        )
        spec.validate(path)
        return spec

    @property
    def variant_id(self) -> str:
        return f"{self.agent_id}:{self.variant}"

    def validate(self, path: str) -> None:
        missing_modalities = set(self.required_modalities) - set(self.supported_modalities)
        if missing_modalities:
            missing = ", ".join(sorted(missing_modalities))
            from snowl_mobile.core.errors import ConfigError

            raise ConfigError(
                f"required_modalities must be a subset of supported_modalities (missing: {missing})",
                path=path,
            )
        if "image" in self.required_modalities and not self.supports_image_input:
            from snowl_mobile.core.errors import ConfigError

            raise ConfigError(
                "supports_image_input must be true when image is required",
                path=f"{path}.supports_image_input",
            )
        if self.requires_tool_calling and not self.supports_tool_calling:
            from snowl_mobile.core.errors import ConfigError

            raise ConfigError(
                "requires_tool_calling cannot be true when supports_tool_calling is false",
                path=f"{path}.requires_tool_calling",
            )
        if self.requires_json_mode and not self.supports_json_mode:
            from snowl_mobile.core.errors import ConfigError

            raise ConfigError(
                "requires_json_mode cannot be true when supports_json_mode is false",
                path=f"{path}.requires_json_mode",
            )

    def model_compatibility_issues(self, model: "ModelSpec") -> list[str]:
        issues: list[str] = []
        if model.api_style not in self.supported_model_protocols:
            issues.append(
                f"model api_style '{model.api_style}' is not in supported_model_protocols"
            )
        missing_modalities = set(self.required_modalities) - set(model.modalities)
        if missing_modalities:
            missing = ", ".join(sorted(missing_modalities))
            issues.append(f"model is missing required modalities: {missing}")
        if "image" in self.required_modalities and not model.supports_image_input:
            issues.append("model does not support image input")
        if self.requires_tool_calling and not model.supports_tool_calling:
            issues.append("model does not support tool calling")
        if self.requires_json_mode and not model.supports_json_mode:
            issues.append("model does not support json mode")
        return issues

    def benchmark_compatibility_issues(self, benchmark: "BenchmarkSpec") -> list[str]:
        issues: list[str] = []
        if benchmark.supported_agent_ids and self.agent_id not in benchmark.supported_agent_ids:
            issues.append(
                f"benchmark '{benchmark.benchmark_id}' does not list agent '{self.agent_id}' as supported"
            )
        if self.supported_backends and benchmark.device_backend not in self.supported_backends:
            issues.append(
                f"benchmark device_backend '{benchmark.device_backend}' is not in agent supported_backends"
            )
        return issues
