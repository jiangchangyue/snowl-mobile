from __future__ import annotations

from snowl_mobile.adapters.agents.base import BaseAgentAdapter, AgentRuntime
from snowl_mobile.core.agent_spec import AgentSpec
from snowl_mobile.core.enums import IntegrationMode, WorkerMode
from snowl_mobile.core.errors import PhaseStubError
from snowl_mobile.core.trial_context import TrialContext


class _DummyAgentRuntime(AgentRuntime):
    def create_session(self) -> None:
        raise PhaseStubError("Dummy agent runtime is a dry-run-only stub.")

    def step(self, observation: object) -> object:
        raise PhaseStubError("Dummy agent runtime is a dry-run-only stub.")

    def close_session(self) -> None:
        raise PhaseStubError("Dummy agent runtime is a dry-run-only stub.")


class DummyTextAgentAdapter(BaseAgentAdapter):
    @property
    def adapter_id(self) -> str:
        return "dummy_text_agent"

    def describe(self) -> AgentSpec:
        return AgentSpec(
            agent_id=self.adapter_id,
            display_name="Dummy Text Agent",
            variant="default",
            model_ref="dummy_text_model",
            integration_mode=IntegrationMode.NATIVE,
            required_modalities=("text",),
            supported_modalities=("text",),
            supported_backends=("adb_appium", "adb"),
            supported_model_protocols=("openai_chat",),
            supports_tool_calling=False,
            supports_image_input=False,
            supports_json_mode=False,
            requires_tool_calling=False,
            requires_json_mode=False,
            required_env=(),
            action_schema="dummy_text_action_v1",
            prompt_contract_version="dummy.v1",
            worker_mode=WorkerMode.IN_PROCESS,
            supported_benchmarks=("androidworld", "dummy_benchmark", "mobilesafetybench"),
        )

    def build_runtime(self, ctx: TrialContext) -> AgentRuntime:
        return _DummyAgentRuntime()


class DummyVisionAgentAdapter(BaseAgentAdapter):
    @property
    def adapter_id(self) -> str:
        return "dummy_vision_agent"

    def describe(self) -> AgentSpec:
        return AgentSpec(
            agent_id=self.adapter_id,
            display_name="Dummy Vision Agent",
            variant="default",
            model_ref="dummy_vision_model",
            integration_mode=IntegrationMode.HYBRID,
            required_modalities=("text", "image"),
            supported_modalities=("text", "image"),
            supported_backends=("adb_appium", "adb"),
            supported_model_protocols=("openai_chat",),
            supports_tool_calling=False,
            supports_image_input=True,
            supports_json_mode=True,
            requires_tool_calling=False,
            requires_json_mode=True,
            required_env=(),
            action_schema="dummy_vision_action_v1",
            prompt_contract_version="dummy.v1",
            worker_mode=WorkerMode.VENV,
            supported_benchmarks=("androidworld", "dummy_benchmark", "mobilesafetybench"),
        )

    def build_runtime(self, ctx: TrialContext) -> AgentRuntime:
        return _DummyAgentRuntime()
