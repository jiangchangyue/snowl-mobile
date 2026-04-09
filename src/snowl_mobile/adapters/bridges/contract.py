from __future__ import annotations

from dataclasses import dataclass, field

from snowl_mobile.core.enums import IntegrationMode
from snowl_mobile.core.errors import IntegrationError


@dataclass(frozen=True, slots=True)
class BridgeContract:
    bridge_id: str
    agent_id: str
    benchmark_id: str
    integration_mode: IntegrationMode = IntegrationMode.WRAP
    observation_mapping_entry: str = ""
    action_mapping_entry: str = ""
    run_entry: str = ""
    environment_handshake_entry: str = ""
    artifact_capture_hooks: tuple[str, ...] = field(default_factory=tuple)
    supported_backends: tuple[str, ...] = field(default_factory=tuple)
    required_env: tuple[str, ...] = field(default_factory=tuple)
    requires_pair_recipe: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "bridge_id": self.bridge_id,
            "agent_id": self.agent_id,
            "benchmark_id": self.benchmark_id,
            "integration_mode": self.integration_mode.value,
            "observation_mapping_entry": self.observation_mapping_entry,
            "action_mapping_entry": self.action_mapping_entry,
            "run_entry": self.run_entry,
            "environment_handshake_entry": self.environment_handshake_entry,
            "artifact_capture_hooks": list(self.artifact_capture_hooks),
            "supported_backends": list(self.supported_backends),
            "required_env": list(self.required_env),
            "requires_pair_recipe": self.requires_pair_recipe,
        }


class BridgeContractValidator:
    def validate(self, contract: BridgeContract) -> BridgeContract:
        required_fields = {
            "bridge_id": contract.bridge_id,
            "agent_id": contract.agent_id,
            "benchmark_id": contract.benchmark_id,
            "observation_mapping_entry": contract.observation_mapping_entry,
            "action_mapping_entry": contract.action_mapping_entry,
            "run_entry": contract.run_entry,
            "environment_handshake_entry": contract.environment_handshake_entry,
        }
        missing = sorted(name for name, value in required_fields.items() if not value.strip())
        if missing:
            joined = ", ".join(missing)
            raise IntegrationError(f"bridge contract is missing required fields: {joined}")
        if not contract.artifact_capture_hooks:
            raise IntegrationError("bridge contract requires at least one artifact_capture_hook")
        return contract
