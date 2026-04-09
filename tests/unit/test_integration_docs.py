from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from snowl_mobile.core.config_loader import load_project_spec


class IntegrationDocsTestCase(unittest.TestCase):
    def test_prompt_docs_reference_current_paths_and_commands(self) -> None:
        cli_source = (ROOT / "src" / "snowl_mobile" / "cli" / "main.py").read_text(encoding="utf-8")
        agent_prompt = (
            ROOT / "docs" / "prompts" / "integrate-agent-prompt.md"
        ).read_text(encoding="utf-8")
        benchmark_prompt = (
            ROOT / "docs" / "prompts" / "integrate-benchmark-prompt.md"
        ).read_text(encoding="utf-8")

        shared_expectations = [
            "AGENTS.md",
            "README-FOR-CODEX.md",
            "CODEX-IMPLEMENTATION-ROADMAP.md",
            "INTEGRATION-CONTRACTS.md",
            "REPOSITORY-BOOTSTRAP.md",
            "README.md",
            "validate-config",
            "plan",
            "dry-run",
            "wrap / native / hybrid",
        ]
        for expected in shared_expectations:
            self.assertIn(expected, agent_prompt)
            self.assertIn(expected, benchmark_prompt)

        self.assertIn("references/agents/<repo_name>/", agent_prompt)
        self.assertIn("inspect-repo agent", agent_prompt)
        self.assertIn("integration-checklist agent", agent_prompt)
        self.assertIn("scaffold-agent-package", agent_prompt)
        self.assertIn("docs/integrate-agent.md", agent_prompt)
        self.assertIn("docs/integrate-pair.md", agent_prompt)

        self.assertIn("references/benchmarks/<repo_name>/", benchmark_prompt)
        self.assertIn("inspect-repo benchmark", benchmark_prompt)
        self.assertIn("integration-checklist benchmark", benchmark_prompt)
        self.assertIn("scaffold-benchmark-package", benchmark_prompt)
        self.assertIn("docs/integrate-benchmark.md", benchmark_prompt)
        self.assertIn("docs/integrate-pair.md", benchmark_prompt)

        for command_name in (
            "validate-config",
            "plan",
            "dry-run",
            "inspect-repo",
            "integration-checklist",
            "scaffold-agent-package",
            "scaffold-benchmark-package",
            "scaffold-bridge-package",
        ):
            self.assertIn(f'"{command_name}"', cli_source)

    def test_readme_contains_required_workflow_sections(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("## First-Time Setup", readme)
        self.assertIn("## First Real Run: Open-AutoGLM x MobileSafetyBench", readme)
        self.assertIn("## Manual And Codex-Assisted Integration Workflows", readme)
        self.assertIn("docs/prompts/integrate-benchmark-prompt.md", readme)
        self.assertIn("docs/prompts/integrate-agent-prompt.md", readme)
        self.assertIn("docs/integration-readiness-checklist.md", readme)
        self.assertIn("docs/quickstart.md", readme)
        self.assertIn("docs/troubleshooting.md", readme)

    def test_readiness_checklist_covers_pre_clone_post_clone_and_validation(self) -> None:
        checklist = (
            ROOT / "docs" / "integration-readiness-checklist.md"
        ).read_text(encoding="utf-8")

        self.assertIn("clone 前需要检查什么", checklist)
        self.assertIn("clone 后需要做什么", checklist)
        self.assertIn("Codex 接入完成后需要验证什么", checklist)
        self.assertIn("references/agents/<repo_name>/", checklist)
        self.assertIn("references/benchmarks/<repo_name>/", checklist)
        self.assertIn("validate-config", checklist)
        self.assertIn("dry-run", checklist)

    def test_future_example_configs_load_under_current_schema(self) -> None:
        benchmark_spec = load_project_spec(
            ROOT / "examples" / "configs" / "future-benchmark-integration.example.yml"
        )
        agent_spec = load_project_spec(
            ROOT / "examples" / "configs" / "future-agent-integration.example.yml"
        )

        self.assertEqual(benchmark_spec.benchmarks[0].benchmark_id, "future_mock_benchmark")
        self.assertEqual(benchmark_spec.benchmarks[0].task_source.kind.value, "reference_repo")
        self.assertEqual(agent_spec.agents[0].agent_id, "future_mock_agent")
        self.assertEqual(agent_spec.agents[0].required_modalities, ("text", "image"))
