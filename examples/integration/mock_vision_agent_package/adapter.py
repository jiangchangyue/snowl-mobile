from __future__ import annotations

from snowl_mobile.adapters.agents.base import AgentRuntime, BaseAgentAdapter
from snowl_mobile.core.agent_spec import AgentSpec
from snowl_mobile.core.enums import IntegrationMode, WorkerMode
from snowl_mobile.core.errors import PhaseStubError
from snowl_mobile.core.trial_context import TrialContext
from snowl_mobile.schemas.observation import ObservationBundle


class _MockVisionAgentAdapterRuntime(AgentRuntime):
    """TODO: fill this runtime after inspecting the real agent repo.

    Repo: `mock-agent-repo`
    Local path: `references/agents/mock-agent-repo`
    Suggested integration mode: `hybrid`
    Capability profile: `vision-capable`
    Inspector summary: Mock Agent Repo This is a local-only mock agent repository used to demonstrate the snowl-mobile integration toolkit. Entrypoints
    """

    def create_session(self) -> None:
        # TODO: initialize the upstream runtime and model client via `mock_agent/model_client.py`.
        raise PhaseStubError("Scaffold only: initialize the upstream runtime here.")

    def step(self, observation: ObservationBundle) -> object:
        # TODO: map ObservationBundle via `examples/run_demo.py`.
        # TODO: run the upstream step entry `examples/run_demo.py` or wrap runner `examples/run_demo.py`.
        # TODO: normalize the raw output through `mock_agent/action_parser.py`.
        raise PhaseStubError("Scaffold only: implement the agent step entry here.")

    def close_session(self) -> None:
        # TODO: close upstream sessions, model clients, and device-control handles.
        raise PhaseStubError("Scaffold only: close the upstream runtime here.")


class MockVisionAgentAdapter(BaseAgentAdapter):
    @property
    def adapter_id(self) -> str:
        return "mock_vision_agent"

    def describe(self) -> AgentSpec:
        return AgentSpec(
            agent_id=self.adapter_id,
            display_name="Mock Vision Agent",
            variant="default",
            model_ref="dummy_vision_model",
            integration_mode=IntegrationMode.HYBRID,
            required_modalities=('text', 'image'),
            supported_modalities=('text', 'image'),
            supported_model_protocols=('openai_chat',),
            supports_tool_calling=False,
            supports_image_input=True,
            supports_json_mode=True,
            requires_tool_calling=False,
            requires_json_mode=False,
            required_env=('requests', 'pillow'),
            action_schema="json_action",
            prompt_contract_version="TODO_prompt_contract",
            worker_mode=WorkerMode.VENV,
            supported_benchmarks=("TODO_benchmark_id",),
        )

    def build_runtime(self, ctx: TrialContext) -> AgentRuntime:
        # TODO: keep device control through `mock_agent/device_controller.py` isolated from core orchestration.
        return _MockVisionAgentAdapterRuntime()
