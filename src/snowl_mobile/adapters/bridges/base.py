from __future__ import annotations

from abc import ABC, abstractmethod

from snowl_mobile.adapters.base import AdapterMetadata, BaseAdapter
from snowl_mobile.adapters.bridges.contract import BridgeContract, BridgeContractValidator
from snowl_mobile.core.trial_context import TrialContext
from snowl_mobile.schemas.observation import ObservationBundle


class BaseBridgeAdapter(BaseAdapter, ABC):
    """Bridge responsibilities stay pair-scoped and narrower than normal adapters.

    A bridge exists only when one agent x benchmark pair needs dedicated glue:

    - observation mapping override
    - action mapping override
    - run entry override
    - environment handshake
    - artifact capture hooks
    """

    kind = "bridge"

    @property
    @abstractmethod
    def agent_id(self) -> str:
        """Agent side of the bridge pair."""

    @property
    @abstractmethod
    def benchmark_id(self) -> str:
        """Benchmark side of the bridge pair."""

    @abstractmethod
    def describe_bridge(self) -> BridgeContract:
        """Return the pair-specific bridge contract for this adapter."""

    def map_observation(self, observation: ObservationBundle) -> ObservationBundle:
        """Optional hook for bridge-specific observation remapping."""
        return observation

    def map_action(self, raw_action: object) -> object:
        """Optional hook for bridge-specific action remapping."""
        return raw_action

    def environment_handshake(self, ctx: TrialContext) -> dict[str, str]:
        """Optional hook for pair-specific environment bootstrap and side-channel handshakes."""
        return {}

    def capture_bridge_artifacts(self, ctx: TrialContext) -> dict[str, str]:
        """Optional hook returning bridge-specific raw artifact refs."""
        return {}

    def metadata(self) -> AdapterMetadata:
        contract = BridgeContractValidator().validate(self.describe_bridge())
        return AdapterMetadata(
            adapter_id=self.adapter_id,
            kind=self.kind,
            integration_mode=contract.integration_mode.value,
            supported_backends=contract.supported_backends,
            required_env=contract.required_env,
            supported_benchmarks=(self.benchmark_id,),
            extra={
                "agent_id": self.agent_id,
                "benchmark_id": self.benchmark_id,
                "requires_pair_recipe": contract.requires_pair_recipe,
                "observation_mapping_entry": contract.observation_mapping_entry,
                "action_mapping_entry": contract.action_mapping_entry,
                "run_entry": contract.run_entry,
                "environment_handshake_entry": contract.environment_handshake_entry,
            },
        )

    @abstractmethod
    def run_trial(self, ctx: TrialContext) -> object:
        """Phase 1 contract stub for pair-specific wrapped trial execution."""


BridgeAdapter = BaseBridgeAdapter
