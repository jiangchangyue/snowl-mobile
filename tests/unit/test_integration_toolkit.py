from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from snowl_mobile.integration.checklist_generator import IntegrationChecklistGenerator
from snowl_mobile.integration.repo_inspector import RepositoryInspector
from snowl_mobile.integration.scaffold_generator import (
    AdapterScaffoldGenerator,
    ScaffoldRequest,
)


AGENT_REPO = ROOT / "references" / "agents" / "mock-agent-repo"
BENCHMARK_REPO = ROOT / "references" / "benchmarks" / "mock-benchmark-repo"


class IntegrationToolkitTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.inspector = RepositoryInspector()

    def test_repo_inspector_detects_mock_agent_repo(self) -> None:
        inspection = self.inspector.inspect(AGENT_REPO, repo_kind="agent")

        self.assertEqual(inspection.repo_name, "mock-agent-repo")
        self.assertIn("README.md", inspection.readme_files)
        self.assertIn("requirements.txt", inspection.requirements_files)
        self.assertIn("pyproject.toml", inspection.project_files)
        self.assertTrue(
            any(
                candidate in inspection.entrypoints
                for candidate in ("mock_agent/cli.py", "pyproject:script:mock-agent=mock_agent.cli:main")
            )
        )
        self.assertEqual(inspection.suggested_integration_mode, "hybrid")
        self.assertIn("requests", inspection.dependency_hints)
        self.assertIn("pillow", inspection.dependency_hints)

    def test_repo_inspector_detects_mock_benchmark_repo(self) -> None:
        inspection = self.inspector.inspect(BENCHMARK_REPO, repo_kind="benchmark")

        self.assertEqual(inspection.repo_name, "mock-benchmark-repo")
        self.assertIn("README.md", inspection.readme_files)
        self.assertIn("requirements.txt", inspection.requirements_files)
        self.assertIn("benchmark_runner.py", inspection.entrypoints)
        self.assertEqual(inspection.suggested_integration_mode, "wrap")

    def test_scaffold_generator_writes_agent_template(self) -> None:
        inspection = self.inspector.inspect(AGENT_REPO, repo_kind="agent")
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "mock_agent_repo_adapter.py"
            result = AdapterScaffoldGenerator().generate(
                ScaffoldRequest(
                    repo_kind="agent",
                    adapter_id="mock_agent_repo",
                    inspection=inspection,
                    output_path=output_path,
                )
            )

            content = output_path.read_text(encoding="utf-8")
            self.assertTrue(output_path.exists())
            self.assertEqual(result.class_name, "MockAgentRepoAdapter")
            self.assertIn("class MockAgentRepoAdapter(BaseAgentAdapter)", content)
            self.assertIn("IntegrationMode.HYBRID", content)
            self.assertIn("required_env=('requests', 'pillow')", content)

    def test_checklist_mentions_local_clone_and_validation_steps(self) -> None:
        inspection = self.inspector.inspect(BENCHMARK_REPO, repo_kind="benchmark")
        checklist = IntegrationChecklistGenerator().generate(
            inspection,
            adapter_id="mock_benchmark_repo",
        )

        markdown = checklist.to_markdown()
        self.assertIn("references/benchmarks/mock-benchmark-repo", markdown)
        self.assertIn("validate-config", markdown)
        self.assertIn("dry-run", markdown)
        self.assertIn("mock_benchmark_repo", markdown)
