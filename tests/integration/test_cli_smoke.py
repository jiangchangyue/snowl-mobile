from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
PROJECT = ROOT / "project.example.yml"
MOCK_AGENT_REPO = ROOT / "references" / "agents" / "mock-agent-repo"
MOCK_BENCHMARK_REPO = ROOT / "references" / "benchmarks" / "mock-benchmark-repo"
REAL_PAIR_CONFIG = ROOT / "configs" / "runs" / "autoglm_mobilesafetybench.yml"


class CLISmokeTestCase(unittest.TestCase):
    def _base_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC)
        return env

    def _real_pair_smoke_env(self) -> dict[str, str]:
        env = self._base_env()
        env["SNOWL_TASK_SELECTOR"] = "task_category=text_message_sending,task_id=high_risk_001,limit=1"
        return env

    def test_validate_command(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "snowl_mobile", "validate-config", str(PROJECT)],
            cwd=ROOT,
            env=self._base_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertIn("Validated project", completed.stdout)
        self.assertIn('"trial_blueprints": 2', completed.stdout)
        self.assertIn('"default_worker_mode": "venv"', completed.stdout)

    def test_cli_package_module_entrypoint_supports_help(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "snowl_mobile.cli", "--help"],
            cwd=ROOT,
            env=self._base_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertIn("usage: snowl-mobile", completed.stdout)
        self.assertIn("registry", completed.stdout)

        registry_completed = subprocess.run(
            [sys.executable, "-m", "snowl_mobile.cli", "registry", "list-benchmarks"],
            cwd=ROOT,
            env=self._base_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(registry_completed.returncode, 0, msg=registry_completed.stderr)
        self.assertIn('"mobilesafetybench"', registry_completed.stdout)

    def test_registry_commands_list_agents_and_benchmarks(self) -> None:
        agent_completed = subprocess.run(
            [sys.executable, "-m", "snowl_mobile", "registry", "list-agents"],
            cwd=ROOT,
            env=self._base_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(agent_completed.returncode, 0, msg=agent_completed.stderr)
        self.assertIn("Registered agent adapters", agent_completed.stdout)
        self.assertIn('"mobile_agent_e"', agent_completed.stdout)
        self.assertIn('"mobile_agent_v3_5"', agent_completed.stdout)
        self.assertIn('"open_autoglm"', agent_completed.stdout)

        benchmark_completed = subprocess.run(
            [sys.executable, "-m", "snowl_mobile", "registry", "list-benchmarks", "--metadata"],
            cwd=ROOT,
            env=self._base_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(benchmark_completed.returncode, 0, msg=benchmark_completed.stderr)
        self.assertIn("Registered benchmark adapters", benchmark_completed.stdout)
        self.assertIn('"androidworld"', benchmark_completed.stdout)
        self.assertIn('"mobilesafetybench"', benchmark_completed.stdout)
        self.assertIn('"integration_mode": "hybrid"', benchmark_completed.stdout)

    def test_plan_command_outputs_plan_summary(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "snowl_mobile", "plan", str(PROJECT)],
            cwd=ROOT,
            env=self._base_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertIn("Planned run", completed.stdout)
        self.assertIn('"status": "PLANNED"', completed.stdout)
        self.assertIn('"planned_trials": 4', completed.stdout)

    def test_dry_run_command_outputs_plan_summary_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "snowl_mobile",
                    "dry-run",
                    str(PROJECT),
                    "--output-dir",
                    temp_dir,
                ],
                cwd=ROOT,
                env=self._base_env(),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            self.assertIn("Dry-run simulated 4 trial(s)", completed.stdout)
            self.assertIn('"status": "COMPLETED"', completed.stdout)
            self.assertIn('"retrying": 0', completed.stdout)

            run_dir = Path(temp_dir) / "plan-demo_run"
            self.assertTrue((run_dir / "manifest.json").exists())
            self.assertTrue((run_dir / "plan.json").exists())
            self.assertTrue((run_dir / "summary.json").exists())
            self.assertTrue((run_dir / "events.jsonl").exists())
            self.assertTrue((run_dir / "run.log").exists())
            self.assertTrue(
                (
                    run_dir
                    / "trials"
                    / "demo_run-dummy_text_agent-dummy_benchmark-dummy-task-001-seed-0001"
                    / "trajectory.json"
                ).exists()
            )

    def test_devices_commands_support_fake_mode_for_cli_smoke(self) -> None:
        list_completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "snowl_mobile",
                "devices",
                "list",
                "--config",
                str(PROJECT),
                "--device-mode",
                "fake",
            ],
            cwd=ROOT,
            env=self._base_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(list_completed.returncode, 0, msg=list_completed.stderr)
        self.assertIn("Discovered 1 device(s) in mode 'fake'", list_completed.stdout)
        self.assertIn('"adb_serial": "emulator-5554"', list_completed.stdout)

        health_completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "snowl_mobile",
                "devices",
                "health-check",
                "--config",
                str(PROJECT),
                "--device-mode",
                "fake",
            ],
            cwd=ROOT,
            env=self._base_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(health_completed.returncode, 0, msg=health_completed.stderr)
        self.assertIn("Health-checked 1 device(s): 1 healthy", health_completed.stdout)
        self.assertIn('"health_status": "HEALTHY"', health_completed.stdout)

    def test_run_command_executes_dummy_pipeline_and_writes_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "demo-run"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "snowl_mobile",
                    "run",
                    str(PROJECT),
                    "--output-dir",
                    str(run_dir),
                ],
                cwd=ROOT,
                env=self._base_env(),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            self.assertIn("[run] Initializing run", completed.stdout)
            self.assertIn("[run] output_dir:", completed.stdout)
            self.assertIn("[run] Expanding execution plan", completed.stdout)
            self.assertIn("[run] Plan ready:", completed.stdout)
            self.assertIn("[run] Task 1/4 started:", completed.stdout)
            self.assertIn("[run] Task 4/4 finished:", completed.stdout)
            self.assertIn("completed with 4 succeeded, 0 failed", completed.stdout)
            self.assertIn("device_mode='fake'", completed.stdout)
            self.assertIn("Summary:", completed.stdout)
            self.assertNotIn('"trials": [', completed.stdout)

            self.assertTrue((run_dir / "manifest.json").exists())
            self.assertTrue((run_dir / "plan.json").exists())
            self.assertTrue((run_dir / "summary.json").exists())
            self.assertTrue((run_dir / "events.jsonl").exists())
            self.assertTrue((run_dir / "project.snapshot.yml").exists())
            summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["counts"]["planned_trials"], 4)
            self.assertEqual(summary["counts"]["completed"], 4)
            self.assertEqual(summary["counts"]["failed"], 0)
            self.assertIn("metrics_summary", summary)
            self.assertEqual(len(summary["trials"]), 4)

    def test_run_command_resumes_existing_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "resume-demo-run"
            base_command = [
                sys.executable,
                "-m",
                "snowl_mobile",
                "run",
                str(PROJECT),
                "--output-dir",
                str(run_dir),
            ]
            first_completed = subprocess.run(
                base_command,
                cwd=ROOT,
                env=self._base_env(),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(first_completed.returncode, 0, msg=first_completed.stderr)

            second_completed = subprocess.run(
                base_command,
                cwd=ROOT,
                env=self._base_env(),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(second_completed.returncode, 0, msg=second_completed.stderr)
            self.assertIn("completed with 4 succeeded, 0 failed", second_completed.stdout)

            run_log = (run_dir / "run.log").read_text(encoding="utf-8")
            self.assertIn("Resuming run", run_log)
            self.assertIn("Skipping completed trial", run_log)

    def test_run_command_accepts_batch_size_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "batch-size-override-demo"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "snowl_mobile",
                    "run",
                    str(PROJECT),
                    "--output-dir",
                    str(run_dir),
                    "--batch-size",
                    "3",
                ],
                cwd=ROOT,
                env=self._base_env(),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            run_log = (run_dir / "run.log").read_text(encoding="utf-8")
            self.assertIn("batch_size=3", run_log)

    def test_run_command_accepts_model_endpoint_and_max_step_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "model-override-demo"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "snowl_mobile",
                    "run",
                    str(REAL_PAIR_CONFIG),
                    "--device-mode",
                    "fake",
                    "--output-dir",
                    str(run_dir),
                    "--model-name",
                    "Qwen2.5-VL-72B-Instruct",
                    "--base-url",
                    "https://example.invalid/v1",
                    "--api-key",
                    "dummy-key",
                    "--max-steps",
                    "7",
                ],
                cwd=ROOT,
                env=self._real_pair_smoke_env(),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            trial_dirs = sorted((run_dir / "trials").iterdir())
            self.assertEqual(len(trial_dirs), 1)
            meta_payload = json.loads((trial_dirs[0] / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta_payload["spec"]["model_id"], "Qwen2.5-VL-72B-Instruct")
            self.assertEqual(meta_payload["spec"]["max_steps"], 7)

    def test_run_command_reruns_failed_trials_when_resuming_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "resume-rerun-failed-demo"
            base_command = [
                sys.executable,
                "-m",
                "snowl_mobile",
                "run",
                str(PROJECT),
                "--output-dir",
                str(run_dir),
            ]
            first_completed = subprocess.run(
                base_command,
                cwd=ROOT,
                env=self._base_env(),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(first_completed.returncode, 0, msg=first_completed.stderr)

            summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
            failed_trial_id = summary["trials"][0]["trial_id"]
            failed_trial_dir = run_dir / "trials" / failed_trial_id
            meta_path = failed_trial_dir / "meta.json"
            score_path = failed_trial_dir / "score.json"
            meta_payload = json.loads(meta_path.read_text(encoding="utf-8"))
            score_payload = json.loads(score_path.read_text(encoding="utf-8"))
            meta_payload["status"] = "FAILED"
            meta_payload["last_error_type"] = "PAIR_RUNTIME_ERROR"
            meta_payload["last_error_message"] = "synthetic failure for resume test"
            score_payload["status"] = "FAILED"
            meta_path.write_text(json.dumps(meta_payload, indent=2, sort_keys=True), encoding="utf-8")
            score_path.write_text(json.dumps(score_payload, indent=2, sort_keys=True), encoding="utf-8")

            second_completed = subprocess.run(
                base_command,
                cwd=ROOT,
                env=self._base_env(),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(second_completed.returncode, 0, msg=second_completed.stderr)
            self.assertIn("completed_trials=3 pending_trials=1 rerun_trials=1", second_completed.stdout)

            rerun_summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(rerun_summary["counts"]["completed"], 4)
            self.assertEqual(rerun_summary["counts"]["failed"], 0)

            run_log = (run_dir / "run.log").read_text(encoding="utf-8")
            self.assertIn("Re-running terminal trial", run_log)

    def test_real_pair_config_can_plan_and_run_in_fake_bridge_mode(self) -> None:
        plan_completed = subprocess.run(
            [sys.executable, "-m", "snowl_mobile", "plan", str(REAL_PAIR_CONFIG)],
            cwd=ROOT,
            env=self._real_pair_smoke_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(plan_completed.returncode, 0, msg=plan_completed.stderr)
        self.assertIn('"bridge_id": "open_autoglm__mobilesafetybench"', plan_completed.stdout)
        self.assertIn('"planned_trials": 1', plan_completed.stdout)

        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "real-pair-fake-run"
            run_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "snowl_mobile",
                    "run",
                    str(REAL_PAIR_CONFIG),
                    "--device-mode",
                    "fake",
                    "--output-dir",
                    str(run_dir),
                ],
                cwd=ROOT,
                env=self._real_pair_smoke_env(),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(run_completed.returncode, 0, msg=run_completed.stderr)
            self.assertIn("completed with 1 succeeded, 0 failed", run_completed.stdout)
            self.assertIn("Summary:", run_completed.stdout)
            self.assertNotIn('"trials": [', run_completed.stdout)

            summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["counts"]["planned_trials"], 1)
            self.assertEqual(summary["counts"]["completed"], 1)
            self.assertEqual(summary["trials"][0]["primary_metric"], 1)
            run_log = (run_dir / "run.log").read_text(encoding="utf-8")
            self.assertIn("Starting platform run", run_log)
            self.assertIn("will run through pair bridge", run_log)

    def test_worker_run_command_executes_workers(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "snowl_mobile", "worker-run", str(PROJECT)],
            cwd=ROOT,
            env=self._base_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertIn("Worker run executed 6 worker attempt(s) across 4 trial(s)", completed.stdout)
        self.assertIn('"execution_mode": "subprocess"', completed.stdout)
        self.assertIn('"error_type": "WORKER_TRANSIENT_ERROR"', completed.stdout)
        self.assertIn('"status": "COMPLETED"', completed.stdout)

    def test_emulator_demo_command_outputs_resource_flow(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "snowl_mobile", "emulator-demo", str(PROJECT)],
            cwd=ROOT,
            env=self._base_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertIn("Emulator demo provisioned 2 fake instance(s)", completed.stdout)
        self.assertIn('"trial_id": "demo_run-dummy_vision_agent-dummy_benchmark-dummy-task-001-seed-0001"', completed.stdout)
        self.assertIn('"queue_blocked_while_busy": true', completed.stdout)
        self.assertIn('"reset_strategy": "restore_snapshot_then_seed"', completed.stdout)
        self.assertIn('"health_status": "HEALTHY"', completed.stdout)

    def test_inspect_repo_command_reports_mock_agent_repo(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "snowl_mobile",
                "inspect-repo",
                "agent",
                str(MOCK_AGENT_REPO),
            ],
            cwd=ROOT,
            env=self._base_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertIn('"repo_name": "mock-agent-repo"', completed.stdout)
        self.assertIn('"suggested_integration_mode": "hybrid"', completed.stdout)
        self.assertIn('"model_entrypoints": [', completed.stdout)
        self.assertIn('"device_control_candidates": [', completed.stdout)

    def test_scaffold_and_checklist_commands_work_for_mock_benchmark_repo(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "mock_benchmark_repo_adapter.py"
            scaffold_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "snowl_mobile",
                    "scaffold-adapter",
                    "benchmark",
                    str(MOCK_BENCHMARK_REPO),
                    "mock_benchmark_repo",
                    "--output",
                    str(output_path),
                ],
                cwd=ROOT,
                env=self._base_env(),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(scaffold_completed.returncode, 0, msg=scaffold_completed.stderr)
            self.assertTrue(output_path.exists())
            self.assertIn("Generated benchmark scaffold", scaffold_completed.stdout)

            checklist_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "snowl_mobile",
                    "integration-checklist",
                    "benchmark",
                    str(MOCK_BENCHMARK_REPO),
                    "--adapter-id",
                    "mock_benchmark_repo",
                ],
                cwd=ROOT,
                env=self._base_env(),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(checklist_completed.returncode, 0, msg=checklist_completed.stderr)
            self.assertIn("Benchmark Integration Checklist", checklist_completed.stdout)
            self.assertIn("references/benchmarks/mock-benchmark-repo", checklist_completed.stdout)

    def test_scaffold_benchmark_package_command_generates_package(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "snowl_mobile",
                    "scaffold-benchmark-package",
                    str(MOCK_BENCHMARK_REPO),
                    "mock_benchmark_repo",
                    "--output-dir",
                    temp_dir,
                ],
                cwd=ROOT,
                env=self._base_env(),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            self.assertIn("Generated benchmark package scaffold", completed.stdout)
            scaffold_root = Path(temp_dir) / "mock_benchmark_repo_package"
            self.assertTrue((scaffold_root / "adapter.py").exists())
            self.assertTrue((scaffold_root / "register.py").exists())
            self.assertTrue((scaffold_root / "contract.json").exists())

    def test_scaffold_agent_package_command_generates_text_and_vision_packages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            text_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "snowl_mobile",
                    "scaffold-agent-package",
                    str(MOCK_AGENT_REPO),
                    "mock_text_agent",
                    "--output-dir",
                    temp_dir,
                    "--capability-profile",
                    "text-only",
                ],
                cwd=ROOT,
                env=self._base_env(),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(text_completed.returncode, 0, msg=text_completed.stderr)
            self.assertIn("Generated agent package scaffold", text_completed.stdout)

            vision_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "snowl_mobile",
                    "scaffold-agent-package",
                    str(MOCK_AGENT_REPO),
                    "mock_vision_agent",
                    "--output-dir",
                    temp_dir,
                    "--capability-profile",
                    "vision-capable",
                ],
                cwd=ROOT,
                env=self._base_env(),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(vision_completed.returncode, 0, msg=vision_completed.stderr)

            text_root = Path(temp_dir) / "mock_text_agent_package"
            vision_root = Path(temp_dir) / "mock_vision_agent_package"
            self.assertTrue((text_root / "adapter.py").exists())
            self.assertTrue((vision_root / "adapter.py").exists())
            self.assertTrue((text_root / "capability.json").exists())
            self.assertTrue((vision_root / "capability.json").exists())

    def test_scaffold_bridge_package_command_generates_package(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "snowl_mobile",
                    "scaffold-bridge-package",
                    "dummy_vision__dummy_benchmark",
                    "--agent-id",
                    "dummy_vision_agent",
                    "--benchmark-id",
                    "dummy_benchmark",
                    "--output-dir",
                    temp_dir,
                    "--integration-mode",
                    "hybrid",
                    "--requires-pair-recipe",
                ],
                cwd=ROOT,
                env=self._base_env(),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            self.assertIn("Generated bridge package scaffold", completed.stdout)
            scaffold_root = Path(temp_dir) / "dummy_vision__dummy_benchmark_package"
            self.assertTrue((scaffold_root / "bridge.py").exists())
            self.assertTrue((scaffold_root / "pair_runtime_recipe.example.yml").exists())
