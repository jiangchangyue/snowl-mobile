from __future__ import annotations

from snowl_mobile.adapters.bridges.base import BaseBridgeAdapter
from snowl_mobile.adapters.bridges.contract import BridgeContract
from snowl_mobile.core.enums import IntegrationMode
from snowl_mobile.core.errors import PhaseStubError
from snowl_mobile.core.trial_context import TrialContext


class DummyVisionBenchmarkBridgeAdapter(BaseBridgeAdapter):
    @property
    def adapter_id(self) -> str:
        return "dummy_vision__dummy_benchmark"

    @property
    def agent_id(self) -> str:
        return "dummy_vision_agent"

    @property
    def benchmark_id(self) -> str:
        return "dummy_benchmark"

    def describe_bridge(self) -> BridgeContract:
        return BridgeContract(
            bridge_id=self.adapter_id,
            agent_id=self.agent_id,
            benchmark_id=self.benchmark_id,
            integration_mode=IntegrationMode.HYBRID,
            observation_mapping_entry="dummy.bridge.map_observation",
            action_mapping_entry="dummy.bridge.map_action",
            run_entry="dummy.bridge.run_trial",
            environment_handshake_entry="dummy.bridge.handshake",
            artifact_capture_hooks=("dummy.bridge.capture_artifacts",),
            supported_backends=("adb_appium", "bridge_runtime"),
            required_env=("DUMMY_BRIDGE_ENABLED",),
            requires_pair_recipe=True,
        )

    def run_trial(self, ctx: TrialContext) -> object:
        raise PhaseStubError("DummyVisionBenchmarkBridgeAdapter is a bridge-contract stub for P11.")
