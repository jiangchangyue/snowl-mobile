from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from snowl_mobile.core.errors import IntegrationError
from snowl_mobile.integration.benchmark_contract import (
    BenchmarkAdapterContract,
    BenchmarkContractValidator,
    NativeMetricMapping,
)
from snowl_mobile.integration.benchmark_inspector import BenchmarkRepositoryInspector
from snowl_mobile.integration.benchmark_scaffold import (
    BenchmarkPackageScaffoldGenerator,
    BenchmarkPackageScaffoldRequest,
)


BENCHMARK_REPO = ROOT / "references" / "benchmarks" / "mock-benchmark-repo"


class BenchmarkIntegrationSupportTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.inspector = BenchmarkRepositoryInspector()

    def test_mock_benchmark_repo_inspection_is_structured(self) -> None:
        inspection = self.inspector.inspect(BENCHMARK_REPO)

        self.assertEqual(inspection.repo_name, "mock-benchmark-repo")
        self.assertIn("examples", inspection.examples_dirs)
        self.assertIn("benchmark_runner.py", inspection.evaluation_entrypoints)
        self.assertIn("tasks/tasks.json", inspection.task_discovery_candidates)
        self.assertIn("reset_env.py", inspection.reset_candidates)
        self.assertIn("scorer.py", inspection.scorer_candidates)
        self.assertIn("ui_tree", inspection.observation_forms)
        self.assertIn("action_executor.py", inspection.action_execution_candidates)
        self.assertIn("artifact_capture.py", inspection.raw_artifact_capture_points)

    def test_benchmark_scaffold_generator_writes_package_layout(self) -> None:
        inspection = self.inspector.inspect(BENCHMARK_REPO)
        with tempfile.TemporaryDirectory() as temp_dir:
            result = BenchmarkPackageScaffoldGenerator().generate(
                BenchmarkPackageScaffoldRequest(
                    adapter_id="mock_benchmark_repo",
                    inspection=inspection,
                    output_dir=Path(temp_dir),
                    integration_mode="wrap",
                )
            )

            self.assertTrue((result.scaffold_root / "adapter.py").exists())
            self.assertTrue((result.scaffold_root / "register.py").exists())
            self.assertTrue((result.scaffold_root / "config.example.yml").exists())
            self.assertTrue((result.scaffold_root / "README.md").exists())
            self.assertTrue((result.scaffold_root / "contract.json").exists())
            self.assertTrue(
                (result.scaffold_root / "tests" / "test_mock_benchmark_repo_integration.py").exists()
            )

            contract_payload = json.loads((result.scaffold_root / "contract.json").read_text(encoding="utf-8"))
            self.assertEqual(contract_payload["run_entry"], "benchmark_runner.py")
            self.assertEqual(contract_payload["score_capture_entry"], "scorer.py")

    def test_contract_validator_rejects_missing_run_entry(self) -> None:
        contract = BenchmarkAdapterContract(
            task_discovery_entry="tasks/tasks.json",
            environment_init_entry="reset_env.py",
            pre_task_setup_entry="prepare_trial",
            reset_entry="reset_env.py",
            run_entry="",
            score_capture_entry="scorer.py",
            cleanup_entry="reset_env.py",
            observation_form="ui_tree",
            action_execution_path="action_executor.py",
            raw_artifact_capture_points=("artifact_capture.py",),
            native_metric_mappings=(
                NativeMetricMapping(
                    native_metric="task_success",
                    platform_metric="task_success",
                ),
            ),
        )

        with self.assertRaises(IntegrationError):
            BenchmarkContractValidator().validate(contract)
