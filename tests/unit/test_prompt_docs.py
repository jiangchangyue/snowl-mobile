from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from snowl_mobile.core.config_loader import load_project_spec


class PromptDocsContractTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.readme_zh = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
        self.cli_source = (ROOT / "src" / "snowl_mobile" / "cli" / "main.py").read_text(
            encoding="utf-8"
        )
        self.benchmark_prompt = (
            ROOT / "docs" / "prompts" / "integrate-benchmark-prompt.md"
        ).read_text(encoding="utf-8")
        self.agent_prompt = (ROOT / "docs" / "prompts" / "integrate-agent-prompt.md").read_text(
            encoding="utf-8"
        )
        self.readiness_checklist = (
            ROOT / "docs" / "integration-readiness-checklist.md"
        ).read_text(encoding="utf-8")
        self.quickstart = (ROOT / "docs" / "quickstart.md").read_text(encoding="utf-8")
        self.troubleshooting = (ROOT / "docs" / "troubleshooting.md").read_text(
            encoding="utf-8"
        )

    def test_benchmark_prompt_matches_current_platform_commands(self) -> None:
        required_strings = (
            "references/benchmarks/<repo_name>/",
            "AGENTS.md",
            "README-FOR-CODEX.md",
            "CODEX-IMPLEMENTATION-ROADMAP.md",
            "INTEGRATION-CONTRACTS.md",
            "REPOSITORY-BOOTSTRAP.md",
            "README.md",
            "docs/integrate-benchmark.md",
            "docs/integrate-pair.md",
            "project.example.yml",
            "inspect-repo benchmark",
            "integration-checklist benchmark",
            "scaffold-benchmark-package",
            "validate-config",
            "plan",
            "dry-run",
            "wrap",
            "native",
            "hybrid",
        )
        for required in required_strings:
            self.assertIn(required, self.benchmark_prompt)

        for command_name in (
            "inspect-repo",
            "integration-checklist",
            "scaffold-benchmark-package",
            "validate-config",
            "plan",
            "dry-run",
        ):
            self.assertIn(command_name, self.cli_source)

    def test_agent_prompt_matches_current_platform_commands(self) -> None:
        required_strings = (
            "references/agents/<repo_name>/",
            "AGENTS.md",
            "README-FOR-CODEX.md",
            "CODEX-IMPLEMENTATION-ROADMAP.md",
            "INTEGRATION-CONTRACTS.md",
            "REPOSITORY-BOOTSTRAP.md",
            "README.md",
            "docs/integrate-agent.md",
            "docs/integrate-pair.md",
            "project.example.yml",
            "inspect-repo agent",
            "integration-checklist agent",
            "scaffold-agent-package",
            "validate-config",
            "plan",
            "dry-run",
            "wrap",
            "native",
            "hybrid",
        )
        for required in required_strings:
            self.assertIn(required, self.agent_prompt)

        for command_name in (
            "inspect-repo",
            "integration-checklist",
            "scaffold-agent-package",
            "validate-config",
            "plan",
            "dry-run",
        ):
            self.assertIn(command_name, self.cli_source)

    def test_readme_and_checklist_expose_end_user_workflows(self) -> None:
        for required in (
            "## First-Time Setup",
            "## First Real Run: Open-AutoGLM x MobileSafetyBench",
            "## Manual And Codex-Assisted Integration Workflows",
            "docs/prompts/integrate-benchmark-prompt.md",
            "docs/prompts/integrate-agent-prompt.md",
            "docs/integration-readiness-checklist.md",
            "docs/quickstart.md",
            "docs/troubleshooting.md",
            "snowl-mobile registry list-agents",
            "snowl-mobile registry list-benchmarks",
        ):
            self.assertIn(required, self.readme)

        for required in (
            "## 第一次使用：完整步骤",
            "## 第一次真实运行 Open-AutoGLM × MobileSafetyBench",
            "## 手工接入与 Codex 辅助接入",
            "registry list-agents",
            "registry list-benchmarks",
        ):
            self.assertIn(required, self.readme_zh)

        for required in (
            "clone 前需要检查什么",
            "clone 后需要做什么",
            "Codex 接入完成后",
            "references/agents/<repo_name>/",
            "references/benchmarks/<repo_name>/",
            "validate-config",
            "dry-run",
        ):
            self.assertIn(required, self.readiness_checklist)

        for required in (
            "snowl-mobile registry list-agents",
            "snowl-mobile registry list-benchmarks",
            "snowl-mobile devices list",
            "snowl-mobile run configs/runs/autoglm_mobilesafetybench.yml",
            "--batch-size 2",
            "--model-name",
        ):
            self.assertIn(required, self.quickstart)

        for required in (
            "PHONE_AGENT_BASE_URL",
            "PHONE_AGENT_API_KEY",
            "APPIUM_BIN",
            "references/benchmarks/mobilesafetybench",
        ):
            self.assertIn(required, self.troubleshooting)

        self.assertNotIn(".env.example", self.readme)
        self.assertNotIn(".env.example", self.readme_zh)

    def test_cli_source_exposes_registry_commands(self) -> None:
        for command_name in (
            "registry",
            "list-agents",
            "list-benchmarks",
            "list-bridges",
        ):
            self.assertIn(command_name, self.cli_source)

    def test_future_example_configs_load_with_current_schema(self) -> None:
        benchmark_spec = load_project_spec(
            ROOT / "examples" / "configs" / "future-benchmark-integration.example.yml"
        )
        agent_spec = load_project_spec(
            ROOT / "examples" / "configs" / "future-agent-integration.example.yml"
        )

        self.assertEqual(benchmark_spec.project.name, "future-benchmark-integration-demo")
        self.assertEqual(agent_spec.project.name, "future-agent-integration-demo")
        self.assertEqual(
            benchmark_spec.benchmarks[0].task_source.path,
            "references/benchmarks/future-mock-benchmark-repo",
        )
        self.assertIn("FUTURE_AGENT_HOME", agent_spec.agents[0].required_env)


if __name__ == "__main__":
    unittest.main()
