from __future__ import annotations

from abc import ABC, abstractmethod

from snowl_mobile.adapters.base import AdapterMetadata, BaseAdapter
from snowl_mobile.core.agent_spec import AgentSpec
from snowl_mobile.core.errors import PhaseStubError
from snowl_mobile.core.trial_context import TrialContext
from snowl_mobile.schemas.observation import ObservationBundle


class AgentRuntime(ABC):
    @abstractmethod
    def create_session(self) -> None:
        """Prepare a runtime session."""

    @abstractmethod
    def step(self, observation: ObservationBundle) -> object:
        """Produce the next action from an observation."""

    @abstractmethod
    def close_session(self) -> None:
        """Tear down the runtime session."""


class BaseAgentAdapter(BaseAdapter, ABC):
    """Recommended agent structure:

    1. `describe()` declares stable capability metadata and model-compatibility constraints.
    2. `build_runtime()` creates the native/hybrid runtime shell without leaking global state.
    3. `transform_observation()` owns upstream observation -> `ObservationBundle` mapping.
    4. the runtime step loop should stay focused on upstream inference/control, not platform logging.
    5. `normalize_action()` should convert raw upstream output into the stable platform action schema.
    6. `capture_raw_output()` should keep raw model/tool traces separate from normalized actions.

    Responsibility boundaries:

    - observation transform: adapter-owned, before platform execution
    - step/run entry: adapter runtime-owned, during upstream interaction
    - action normalization: adapter-owned, after raw output is produced
    - raw output capture: adapter-owned, persisted separately for audit/debug
    - model compatibility declaration: adapter-owned via `AgentSpec`
    """

    kind = "agent"

    @abstractmethod
    def describe(self) -> AgentSpec:
        """Return the canonical AgentSpec exposed by this adapter."""

    @abstractmethod
    def build_runtime(self, ctx: TrialContext) -> AgentRuntime:
        """Build a runtime object for native/hybrid execution paths."""

    def transform_observation(self, observation: ObservationBundle) -> ObservationBundle:
        """Optional hook for normalizing upstream observations before the step loop."""
        return observation

    def normalize_action(self, raw_output: object) -> object:
        """Optional hook for mapping upstream raw output into a stable action schema."""
        return raw_output

    def capture_raw_output(self, raw_output: object) -> dict[str, str]:
        """Optional hook returning refs to raw model output artifacts."""
        return {}

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
            },
        )


class WrappedAgentAdapter(BaseAgentAdapter, ABC):
    def build_runtime(self, ctx: TrialContext) -> AgentRuntime:
        raise PhaseStubError("WrappedAgentAdapter does not expose build_runtime in this phase.")

    def run_trial(self, ctx: TrialContext) -> object:
        """Phase 1 contract stub for wrap-mode trial execution."""


AgentAdapter = BaseAgentAdapter
