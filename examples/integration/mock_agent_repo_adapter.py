from __future__ import annotations

from snowl_mobile.adapters.agents.base import AgentRuntime, BaseAgentAdapter
from snowl_mobile.core.agent_spec import AgentSpec
from snowl_mobile.core.enums import IntegrationMode, WorkerMode
from snowl_mobile.core.errors import PhaseStubError
from snowl_mobile.core.trial_context import TrialContext
from snowl_mobile.schemas.observation import ObservationBundle


class _MockAgentRepoAdapterRuntime(AgentRuntime):
    """Placeholder runtime for `mock-agent-repo`.

    Local repo path: `references/agents/mock-agent-repo`
    Inspector summary: Mock Agent Repo This is a local-only mock agent repository used to demonstrate the snowl-mobile integration toolkit. Entrypoint
    """

    def create_session(self) -> None:
        raise PhaseStubError("Scaffold only: wire the upstream runtime or wrap runner here.")

    def step(self, observation: ObservationBundle) -> object:
        # TODO: transform ObservationBundle into the upstream repo input format.
        # TODO: parse the upstream action output back into the platform action schema.
        raise PhaseStubError("Scaffold only: implement the agent step loop here.")

    def close_session(self) -> None:
        raise PhaseStubError("Scaffold only: close upstream sessions or subprocess handles here.")


class MockAgentRepoAdapter(BaseAgentAdapter):
    @property
    def adapter_id(self) -> str:
        return "mock_agent_repo"

    def describe(self) -> AgentSpec:
        return AgentSpec(
            agent_id=self.adapter_id,
            display_name="Mock Agent Repo",
            variant="default",
            model_ref="TODO_model_binding",
            integration_mode=IntegrationMode.HYBRID,
            required_modalities=('text',),
            supported_modalities=('text', 'image'),
            supported_model_protocols=("openai_chat",),
            supports_tool_calling=False,
            supports_image_input=True,
            supports_json_mode=True,
            requires_tool_calling=False,
            requires_json_mode=False,
            required_env=('requests', 'pillow'),
            action_schema="TODO_action_schema",
            prompt_contract_version="TODO_prompt_contract",
            worker_mode=WorkerMode.VENV,
            supported_benchmarks=('TODO_benchmark_id',),
        )

    def build_runtime(self, ctx: TrialContext) -> AgentRuntime:
        # TODO: choose wrap/native/hybrid execution explicitly.
        # TODO: keep env setup in RuntimeRecipe / worker isolation, not in global imports.
        return _MockAgentRepoAdapterRuntime()
