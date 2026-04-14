from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from snowl_mobile.adapters.benchmarks.mobilesafetybench import (
    MobileSafetyBenchBenchmarkAdapter,
    build_mobilesafetybench_report,
)
from snowl_mobile.adapters.builtin import create_builtin_registry
from snowl_mobile.core.config_loader import load_project_spec
from snowl_mobile.core.run_context import RunContext
from snowl_mobile.core.states import TrialStatus
from snowl_mobile.core.trial_context import TrialContext
from snowl_mobile.core.trial_spec import TrialSpec
from snowl_mobile.integration.benchmark_inspector import BenchmarkRepositoryInspector


MOBILE_SAFETY_BENCH_REPO = ROOT / "references" / "benchmarks" / "mobilesafetybench"
MOBILE_SAFETY_BENCH_CONFIG = ROOT / "configs" / "runs" / "autoglm_mobilesafetybench.yml"


class MobileSafetyBenchAdapterTestCase(unittest.TestCase):
    def test_builtin_registry_registers_mobilesafetybench_adapter(self) -> None:
        registry = create_builtin_registry()

        entry = registry.resolve_benchmark("mobilesafetybench")

        self.assertEqual(entry.adapter_id, "mobilesafetybench")
        self.assertEqual(entry.metadata.integration_mode, "hybrid")
        self.assertIn("MOBILE_SAFETY_HOME", entry.metadata.required_env)

    def test_repo_inspection_reports_real_benchmark_structure(self) -> None:
        inspection = BenchmarkRepositoryInspector().inspect(MOBILE_SAFETY_BENCH_REPO)

        self.assertEqual(inspection.repo_name, "mobilesafetybench")
        self.assertEqual(inspection.suggested_integration_mode, "wrap")
        self.assertIn("asset/tasks/tasks.json", inspection.task_discovery_candidates)
        self.assertIn("mobile_safety/environment.py", inspection.evaluation_entrypoints)
        self.assertIn("mobile_safety/environment.py", inspection.environment_init_candidates)
        self.assertIn("mobile_safety/component/parser.py", inspection.action_execution_candidates)
        self.assertIn("mobile_safety/logger.py", inspection.raw_artifact_capture_points)

    def test_mock_wrapped_task_writes_raw_outputs_and_scores(self) -> None:
        adapter = MobileSafetyBenchBenchmarkAdapter()
        report = build_mobilesafetybench_report()
        with mock.patch.dict(
            os.environ,
            {"SNOWL_TASK_SELECTOR": "task_category=text_message_sending,task_id=high_risk_001,limit=1"},
            clear=False,
        ):
            spec = load_project_spec(MOBILE_SAFETY_BENCH_CONFIG)
        run_context = RunContext(
            run_id="mobilesafetybench-test-run",
            project_snapshot=spec,
            artifact_root=ROOT / "runs" / "mobilesafetybench-test-run",
        )
        benchmark = spec.benchmarks[0]
        agent = spec.agents[0]
        task_payload = adapter.list_tasks(run_context)[0]
        self.assertIn("initial_device_status", task_payload)
        self.assertIn("evaluation", task_payload)
        self.assertIn("action_space", task_payload)
        trial_spec = TrialSpec(
            trial_id="mobilesafetybench-trial-001",
            run_id="mobilesafetybench-test-run",
            benchmark_id=benchmark.benchmark_id,
            task_id=str(task_payload["task_id"]),
            agent_id=agent.agent_id,
            agent_variant=agent.variant,
            model_id=agent.model_ref,
            seed="seed-0001",
            status=TrialStatus.PENDING,
            artifact_level=spec.artifacts.level,
            runtime_recipe=spec.build_runtime_recipe(agent, benchmark),
            timeout_sec=spec.runtime.timeout_sec,
            max_steps=spec.runtime.max_steps,
        )
        ctx = TrialContext(trial_spec=trial_spec)

        adapter.prepare_trial(ctx)
        adapter.seed_environment(ctx)
        initial_observation = adapter.get_initial_observation(ctx)
        self.assertEqual(initial_observation.source_backend, "mobilesafetybench_mock")
        self.assertEqual(initial_observation.extra["task_category"], "text_message_sending")
        self.assertIn("initial_device_status", initial_observation.extra)
        self.assertIn("evaluation", initial_observation.extra)

        with tempfile.TemporaryDirectory() as temp_dir:
            request = adapter.build_run_request(ctx, output_dir=Path(temp_dir), mock_mode=True)
            result = adapter.run_wrapped_task(request)

            self.assertEqual(result.task.task_category, "text_message_sending")
            self.assertEqual(result.task.task_id, "high_risk_001")
            self.assertEqual(result.score_bundle.primary_metric, 1)
            self.assertEqual(result.score_bundle.platform_metrics["task_success"], 1)
            self.assertEqual(result.score_bundle.platform_metrics["safety_success"], 1)
            self.assertEqual(result.score_bundle.platform_metrics["helpfulness_success"], 0)
            self.assertTrue(Path(result.raw_artifacts["wrapped_result_path"]).exists())
            self.assertTrue(Path(result.raw_artifacts["logger_path"]).exists())
            self.assertTrue(Path(result.raw_artifacts["xml_stub_path"]).exists())
            self.assertTrue(Path(result.raw_artifacts["screenshot_stub_path"]).exists())
            self.assertEqual(report.recommended_integration_mode, "hybrid")

    def test_selector_limit_minus_one_means_no_limit(self) -> None:
        adapter = MobileSafetyBenchBenchmarkAdapter()
        tasks = adapter._load_tasks()

        selected = adapter._apply_selector(tasks, "task_category=text_message_sending,limit=-1")

        expected = tuple(task for task in tasks if task.task_category == "text_message_sending")
        self.assertEqual(selected, expected)


if __name__ == "__main__":
    unittest.main()
