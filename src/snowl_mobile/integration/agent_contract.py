from __future__ import annotations

from dataclasses import dataclass

from snowl_mobile.core.errors import IntegrationError
from snowl_mobile.models.model_spec import ModelSpec


@dataclass(frozen=True, slots=True)
class AgentCapabilityDeclaration:
    input_modalities: tuple[str, ...]
    action_output_schema: str
    supported_model_protocols: tuple[str, ...]
    tool_backends: tuple[str, ...]
    runtime_requirements: tuple[str, ...]
    human_confirmation_mode: str
    raw_output_capture_points: tuple[str, ...]
    supports_image_input: bool = False
    supports_tool_calling: bool = False
    supports_json_mode: bool = False
    requires_tool_calling: bool = False
    requires_json_mode: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "input_modalities": list(self.input_modalities),
            "action_output_schema": self.action_output_schema,
            "supported_model_protocols": list(self.supported_model_protocols),
            "tool_backends": list(self.tool_backends),
            "runtime_requirements": list(self.runtime_requirements),
            "human_confirmation_mode": self.human_confirmation_mode,
            "raw_output_capture_points": list(self.raw_output_capture_points),
            "supports_image_input": self.supports_image_input,
            "supports_tool_calling": self.supports_tool_calling,
            "supports_json_mode": self.supports_json_mode,
            "requires_tool_calling": self.requires_tool_calling,
            "requires_json_mode": self.requires_json_mode,
        }

    def compatibility_issues(self, model: ModelSpec) -> list[str]:
        issues: list[str] = []
        if model.api_style not in self.supported_model_protocols:
            issues.append(
                f"model api_style '{model.api_style}' is not in supported_model_protocols"
            )
        missing_modalities = set(self.input_modalities) - set(model.modalities)
        if missing_modalities:
            missing = ", ".join(sorted(missing_modalities))
            issues.append(f"model is missing required modalities: {missing}")
        if "image" in self.input_modalities and not model.supports_image_input:
            issues.append("model does not support image input")
        if self.requires_tool_calling and not model.supports_tool_calling:
            issues.append("model does not support tool calling")
        if self.requires_json_mode and not model.supports_json_mode:
            issues.append("model does not support json mode")
        return issues


@dataclass(frozen=True, slots=True)
class AgentAdapterContract:
    observation_transform_entry: str
    step_entry: str
    run_entry: str
    action_normalization_entry: str
    model_call_entry: str
    device_control_entry: str
    raw_output_capture_points: tuple[str, ...]
    capability: AgentCapabilityDeclaration

    def to_dict(self) -> dict[str, object]:
        return {
            "observation_transform_entry": self.observation_transform_entry,
            "step_entry": self.step_entry,
            "run_entry": self.run_entry,
            "action_normalization_entry": self.action_normalization_entry,
            "model_call_entry": self.model_call_entry,
            "device_control_entry": self.device_control_entry,
            "raw_output_capture_points": list(self.raw_output_capture_points),
            "capability": self.capability.to_dict(),
        }


class AgentContractValidator:
    """Validate an agent integration contract and its capability declaration."""

    def validate(self, contract: AgentAdapterContract) -> AgentAdapterContract:
        required_fields = {
            "observation_transform_entry": contract.observation_transform_entry,
            "step_entry": contract.step_entry,
            "run_entry": contract.run_entry,
            "action_normalization_entry": contract.action_normalization_entry,
            "model_call_entry": contract.model_call_entry,
            "device_control_entry": contract.device_control_entry,
        }
        missing = sorted(name for name, value in required_fields.items() if not value.strip())
        if missing:
            joined = ", ".join(missing)
            raise IntegrationError(f"agent contract is missing required fields: {joined}")
        if not contract.raw_output_capture_points:
            raise IntegrationError("agent contract requires at least one raw_output_capture_point")
        self.validate_capability(contract.capability)
        return contract

    def validate_capability(self, capability: AgentCapabilityDeclaration) -> AgentCapabilityDeclaration:
        if not capability.input_modalities:
            raise IntegrationError("agent capability requires at least one input modality")
        if not capability.supported_model_protocols:
            raise IntegrationError("agent capability requires at least one supported model protocol")
        if not capability.tool_backends:
            raise IntegrationError("agent capability requires at least one tool backend")
        if not capability.raw_output_capture_points:
            raise IntegrationError("agent capability requires at least one raw output capture point")
        if "image" in capability.input_modalities and not capability.supports_image_input:
            raise IntegrationError("vision-capable agents must set supports_image_input=true")
        if capability.requires_tool_calling and not capability.supports_tool_calling:
            raise IntegrationError("requires_tool_calling cannot be true when supports_tool_calling is false")
        if capability.requires_json_mode and not capability.supports_json_mode:
            raise IntegrationError("requires_json_mode cannot be true when supports_json_mode is false")
        return capability
