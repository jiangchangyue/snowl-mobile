from __future__ import annotations

from snowl_mobile.adapters.bridges.base import BaseBridgeAdapter
from snowl_mobile.adapters.bridges.contract import BridgeContract
from snowl_mobile.core.enums import IntegrationMode
from snowl_mobile.core.errors import PhaseStubError
from snowl_mobile.core.trial_context import TrialContext
from snowl_mobile.schemas.observation import ObservationBundle


class DummyVisionDummyBenchmarkBridgeAdapter(BaseBridgeAdapter):
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
            observation_mapping_entry="TODO_observation_mapping_entry",
            action_mapping_entry="TODO_action_mapping_entry",
            run_entry="TODO_run_entry",
            environment_handshake_entry="TODO_environment_handshake_entry",
            artifact_capture_hooks=("TODO_artifact_capture_hook",),
            supported_backends=("TODO_backend",),
            required_env=("TODO_ENV_VAR",),
            requires_pair_recipe=True,
        )

    def map_observation(self, observation: ObservationBundle) -> ObservationBundle:
        # TODO: remap benchmark-native observation payloads for this pair only.
        return observation

    def map_action(self, raw_action: object) -> object:
        # TODO: normalize pair-specific action schema mismatches here.
        return raw_action

    def environment_handshake(self, ctx: TrialContext) -> dict[str, str]:
        # TODO: reserve ports, inject pair env vars, and prepare any sidecar hints here.
        return {}

    def capture_bridge_artifacts(self, ctx: TrialContext) -> dict[str, str]:
        # TODO: return pair-specific raw artifact refs for debugging.
        return {}

    def run_trial(self, ctx: TrialContext) -> object:
        raise PhaseStubError("Scaffold only: implement pair-specific bridge run logic here.")
