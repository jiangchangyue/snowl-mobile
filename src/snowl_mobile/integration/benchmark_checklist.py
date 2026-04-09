from __future__ import annotations

from snowl_mobile.integration.benchmark_inspector import BenchmarkRepositoryInspection
from snowl_mobile.integration.checklist_generator import ChecklistItem, IntegrationChecklist


class BenchmarkIntegrationChecklistGenerator:
    def generate(
        self,
        inspection: BenchmarkRepositoryInspection,
        *,
        adapter_id: str | None = None,
    ) -> IntegrationChecklist:
        resolved_adapter_id = adapter_id or inspection.repo_name.replace("-", "_")
        clone_path = f"references/benchmarks/{inspection.repo_name}"
        contract = inspection.default_contract()
        items = [
            ChecklistItem(
                code="B1",
                title="Place the repository under the fixed references path",
                description=(
                    f"Make sure the user cloned the benchmark repo to `{clone_path}`; "
                    "Codex should analyze that local checkout instead of cloning by default."
                ),
            ),
            ChecklistItem(
                code="B2",
                title="Confirm task discovery entry",
                description=(
                    f"Current best candidate: `{contract.task_discovery_entry}`. "
                    "Verify this is the real task manifest, dataset loader, or scenario entry."
                ),
            ),
            ChecklistItem(
                code="B3",
                title="Confirm environment init and reset entries",
                description=(
                    f"Environment init candidate: `{contract.environment_init_entry}`; "
                    f"reset candidate: `{contract.reset_entry}`."
                ),
            ),
            ChecklistItem(
                code="B4",
                title="Confirm run and scorer entrypoints",
                description=(
                    f"Run entry candidate: `{contract.run_entry}`; "
                    f"score capture candidate: `{contract.score_capture_entry}`."
                ),
            ),
            ChecklistItem(
                code="B5",
                title="Confirm observation form and action execution path",
                description=(
                    f"Observation form: `{contract.observation_form}`; "
                    f"action execution path: `{contract.action_execution_path}`."
                ),
            ),
            ChecklistItem(
                code="B6",
                title="Confirm raw artifact capture points",
                description=(
                    "Review these candidate capture points before implementation: "
                    + ", ".join(f"`{entry}`" for entry in contract.raw_artifact_capture_points)
                ),
            ),
            ChecklistItem(
                code="B7",
                title="Generate the benchmark scaffold package",
                description=(
                    f"Use the scaffold package generator for `{resolved_adapter_id}` so adapter, register file, config example, tests, and docs stay aligned."
                ),
            ),
            ChecklistItem(
                code="B8",
                title="Map native metrics into platform metrics explicitly",
                description=(
                    "Keep benchmark-native metrics in ScoreBundle.native_metrics, then add platform-level run/retry/device metrics separately."
                ),
            ),
            ChecklistItem(
                code="B9",
                title="Run minimal validation",
                description=(
                    "Run `validate-config`, `plan`, `dry-run`, and a benchmark-specific smoke integration test before touching real execution."
                ),
            ),
        ]
        return IntegrationChecklist(
            repo_name=inspection.repo_name,
            repo_kind="benchmark",
            clone_path=clone_path,
            adapter_id=resolved_adapter_id,
            suggested_integration_mode=inspection.suggested_integration_mode,
            items=tuple(items),
        )
