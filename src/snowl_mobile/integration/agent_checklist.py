from __future__ import annotations

from snowl_mobile.integration.agent_inspector import AgentRepositoryInspection
from snowl_mobile.integration.checklist_generator import ChecklistItem, IntegrationChecklist


class AgentIntegrationChecklistGenerator:
    def generate(
        self,
        inspection: AgentRepositoryInspection,
        *,
        adapter_id: str | None = None,
        capability_profile: str = "auto",
    ) -> IntegrationChecklist:
        resolved_adapter_id = adapter_id or inspection.repo_name.replace("-", "_")
        clone_path = f"references/agents/{inspection.repo_name}"
        contract = inspection.default_contract(capability_profile=capability_profile)
        items = [
            ChecklistItem(
                code="A1",
                title="Place the repository under the fixed references path",
                description=(
                    f"Make sure the user cloned the agent repo to `{clone_path}`; "
                    "Codex should analyze that local checkout instead of cloning by default."
                ),
            ),
            ChecklistItem(
                code="A2",
                title="Confirm input modalities and observation transform",
                description=(
                    f"Current modalities: `{', '.join(contract.capability.input_modalities)}`; "
                    f"observation transform candidate: `{contract.observation_transform_entry}`."
                ),
            ),
            ChecklistItem(
                code="A3",
                title="Confirm action schema and normalization entry",
                description=(
                    f"Action schema candidate: `{contract.capability.action_output_schema}`; "
                    f"normalization entry: `{contract.action_normalization_entry}`."
                ),
            ),
            ChecklistItem(
                code="A4",
                title="Confirm model protocol and model-call entry",
                description=(
                    f"Supported protocol candidates: `{', '.join(contract.capability.supported_model_protocols)}`; "
                    f"model call entry: `{contract.model_call_entry}`."
                ),
            ),
            ChecklistItem(
                code="A5",
                title="Confirm tool backend and device control entry",
                description=(
                    f"Tool backends: `{', '.join(contract.capability.tool_backends)}`; "
                    f"device control entry: `{contract.device_control_entry}`."
                ),
            ),
            ChecklistItem(
                code="A6",
                title="Confirm runtime requirements and human confirmation behavior",
                description=(
                    f"Runtime requirements: `{', '.join(contract.capability.runtime_requirements) or 'none'}`; "
                    f"human confirmation mode: `{contract.capability.human_confirmation_mode}`."
                ),
            ),
            ChecklistItem(
                code="A7",
                title="Confirm raw output capture points",
                description=(
                    "Review these candidate raw-output capture points before implementation: "
                    + ", ".join(f"`{entry}`" for entry in contract.raw_output_capture_points)
                ),
            ),
            ChecklistItem(
                code="A8",
                title="Generate the agent scaffold package",
                description=(
                    f"Use the scaffold package generator for `{resolved_adapter_id}` so adapter, register file, capability declaration, config example, docs, and tests stay aligned."
                ),
            ),
            ChecklistItem(
                code="A9",
                title="Run minimal validation",
                description=(
                    "Run `validate-config`, `plan`, `dry-run`, and an agent-specific smoke integration test before touching real device control."
                ),
            ),
        ]
        return IntegrationChecklist(
            repo_name=inspection.repo_name,
            repo_kind="agent",
            clone_path=clone_path,
            adapter_id=resolved_adapter_id,
            suggested_integration_mode=inspection.suggested_integration_mode,
            items=tuple(items),
        )
