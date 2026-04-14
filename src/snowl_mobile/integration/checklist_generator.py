from __future__ import annotations

from dataclasses import dataclass

from snowl_mobile.integration.repo_inspector import RepositoryInspection


@dataclass(frozen=True, slots=True)
class ChecklistItem:
    code: str
    title: str
    description: str


@dataclass(frozen=True, slots=True)
class IntegrationChecklist:
    repo_name: str
    repo_kind: str
    clone_path: str
    adapter_id: str
    suggested_integration_mode: str
    items: tuple[ChecklistItem, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "repo_name": self.repo_name,
            "repo_kind": self.repo_kind,
            "clone_path": self.clone_path,
            "adapter_id": self.adapter_id,
            "suggested_integration_mode": self.suggested_integration_mode,
            "items": [
                {
                    "code": item.code,
                    "title": item.title,
                    "description": item.description,
                }
                for item in self.items
            ],
        }

    def to_markdown(self) -> str:
        lines = [
            f"# {self.repo_kind.title()} Integration Checklist",
            "",
            f"- Repo: `{self.repo_name}`",
            f"- Clone path: `{self.clone_path}`",
            f"- Adapter ID: `{self.adapter_id}`",
            f"- Suggested integration mode: `{self.suggested_integration_mode}`",
            "",
        ]
        for item in self.items:
            lines.append(f"- [{item.code}] {item.title}: {item.description}")
        return "\n".join(lines)


class IntegrationChecklistGenerator:
    def generate(
        self,
        inspection: RepositoryInspection,
        *,
        adapter_id: str | None = None,
    ) -> IntegrationChecklist:
        resolved_adapter_id = adapter_id or inspection.repo_name.replace("-", "_")
        clone_root = "references/agents" if inspection.repo_kind == "agent" else "references/benchmarks"
        clone_path = f"{clone_root}/{inspection.repo_name}"
        if inspection.repo_kind == "agent":
            items = self._agent_items(inspection, clone_path, resolved_adapter_id)
        else:
            items = self._benchmark_items(inspection, clone_path, resolved_adapter_id)
        return IntegrationChecklist(
            repo_name=inspection.repo_name,
            repo_kind=inspection.repo_kind,
            clone_path=clone_path,
            adapter_id=resolved_adapter_id,
            suggested_integration_mode=inspection.suggested_integration_mode,
            items=tuple(items),
        )

    def _agent_items(
        self,
        inspection: RepositoryInspection,
        clone_path: str,
        adapter_id: str,
    ) -> list[ChecklistItem]:
        return [
            ChecklistItem(
                code="A1",
                title="Place the repository under the fixed references path",
                description=(
                    f"Make sure the user cloned the upstream agent repo to `{clone_path}`; "
                    "Codex should analyze that local copy instead of cloning by default."
                ),
            ),
            ChecklistItem(
                code="A2",
                title="Inspect README, dependency manifests, and runnable entrypoints",
                description=(
                    f"Review {len(inspection.readme_files)} README file(s), "
                    f"{len(inspection.requirements_files)} dependency manifest(s), and "
                    f"{len(inspection.entrypoints)} entrypoint candidate(s) before choosing an adapter path."
                ),
            ),
            ChecklistItem(
                code="A3",
                title="Choose wrap, native, or hybrid explicitly",
                description=(
                    f"Start from `{inspection.suggested_integration_mode}` unless the repo exposes a cleaner API than the inspector suggests."
                ),
            ),
            ChecklistItem(
                code="A4",
                title="Implement AgentSpec metadata completely",
                description=(
                    "Declare required_env, supported_model_protocols, supported_modalities, "
                    "worker_mode, and any tool-calling / json-mode requirements."
                ),
            ),
            ChecklistItem(
                code="A5",
                title="Implement runtime hooks and observation-to-action handling",
                description=(
                    "Map upstream observation objects into ObservationBundle, translate the agent output into the platform action schema, "
                    "and keep wrap/native boundaries explicit."
                ),
            ),
            ChecklistItem(
                code="A6",
                title="Register the adapter and add a minimal example config",
                description=(
                    f"Register `{adapter_id}` in the registry path used by the project, then add a local example config and smoke test."
                ),
            ),
            ChecklistItem(
                code="A7",
                title="Run minimal validation",
                description=(
                    "Run `validate-config`, `dry-run`, and a smoke integration test before attempting any real benchmark execution."
                ),
            ),
        ]

    def _benchmark_items(
        self,
        inspection: RepositoryInspection,
        clone_path: str,
        adapter_id: str,
    ) -> list[ChecklistItem]:
        return [
            ChecklistItem(
                code="B1",
                title="Place the repository under the fixed references path",
                description=(
                    f"Make sure the user cloned the upstream benchmark repo to `{clone_path}`; "
                    "Codex should work from that local checkout instead of cloning by default."
                ),
            ),
            ChecklistItem(
                code="B2",
                title="Inspect task sources, scorer hooks, reset logic, and entrypoints",
                description=(
                    f"Review {len(inspection.readme_files)} README file(s), "
                    f"{len(inspection.entrypoints)} runner/scorer entrypoint candidate(s), and "
                    "any task manifests before deciding how to expose list_tasks and native scoring."
                ),
            ),
            ChecklistItem(
                code="B3",
                title="Choose wrap, native, or hybrid explicitly",
                description=(
                    f"Start from `{inspection.suggested_integration_mode}` unless the benchmark already exposes a clean Python task API."
                ),
            ),
            ChecklistItem(
                code="B4",
                title="Implement BenchmarkSpec metadata completely",
                description=(
                    "Declare task_source, scorer_ref, reset_policy, reset_requirements, device_backend, and supported_agent_ids."
                ),
            ),
            ChecklistItem(
                code="B5",
                title="Implement task discovery, observation transform, and scoring boundaries",
                description=(
                    "Keep list_tasks, environment seeding, observation extraction, and native scoring in explicit adapter methods so later real execution stays auditable."
                ),
            ),
            ChecklistItem(
                code="B6",
                title="Register the adapter and add a minimal example config",
                description=(
                    f"Register `{adapter_id}` in the registry path used by the project, then add a local example config and smoke test."
                ),
            ),
            ChecklistItem(
                code="B7",
                title="Run minimal validation",
                description=(
                    "Run `validate-config`, `dry-run`, and a smoke integration test before wiring any real emulator-specific setup."
                ),
            ),
        ]
