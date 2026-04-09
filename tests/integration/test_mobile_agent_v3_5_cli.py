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
CONFIG = ROOT / "configs" / "integrations" / "mobile_agent_v3_5" / "minimal.yml"
RUN_CONFIG = ROOT / "configs" / "runs" / "mobile_agent_v3_5_mobilesafetybench.yml"
REPO = ROOT / "references" / "agents" / "MobileAgent" / "Mobile-Agent-v3.5"


class MobileAgentV35CLITestCase(unittest.TestCase):
    def _base_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC)
        return env

    def _smoke_env(self) -> dict[str, str]:
        env = self._base_env()
        env["SNOWL_TASK_SELECTOR"] = "task_category=text_message_sending,task_id=low_risk_001,limit=1"
        return env

    def test_inspect_repo_command_reports_mobile_agent_v3_5(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "snowl_mobile",
                "inspect-repo",
                "agent",
                str(REPO),
            ],
            cwd=ROOT,
            env=self._base_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertIn('"repo_name": "Mobile-Agent-v3.5"', completed.stdout)
        self.assertIn('"suggested_integration_mode": "hybrid"', completed.stdout)
        self.assertIn('"mobile_use/run_gui_owl_1_5_for_mobile.py"', completed.stdout)

    def test_registry_list_agents_metadata_includes_mobile_agent_v3_5(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "snowl_mobile", "registry", "list-agents", "--metadata"],
            cwd=ROOT,
            env=self._base_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertIn('"mobile_agent_v3_5"', completed.stdout)
        self.assertIn('"coordinate_space": "relative_0_1000"', completed.stdout)
        self.assertIn('"integration_mode": "wrap"', completed.stdout)

    def test_validate_plan_and_dry_run_work_with_mobile_agent_v3_5_config(self) -> None:
        validate_completed = subprocess.run(
            [sys.executable, "-m", "snowl_mobile", "validate-config", str(CONFIG)],
            cwd=ROOT,
            env=self._base_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(validate_completed.returncode, 0, msg=validate_completed.stderr)
        self.assertIn('"agent_id": "mobile_agent_v3_5"', validate_completed.stdout)
        self.assertIn('"integration_mode": "wrap"', validate_completed.stdout)

        plan_completed = subprocess.run(
            [sys.executable, "-m", "snowl_mobile", "plan", str(CONFIG)],
            cwd=ROOT,
            env=self._base_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(plan_completed.returncode, 0, msg=plan_completed.stderr)
        self.assertIn('"agent_id": "mobile_agent_v3_5"', plan_completed.stdout)
        self.assertIn('"benchmark_id": "mobilesafetybench"', plan_completed.stdout)
        self.assertIn('"planned_trials": 1', plan_completed.stdout)

        with tempfile.TemporaryDirectory() as temp_dir:
            dry_run_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "snowl_mobile",
                    "dry-run",
                    str(CONFIG),
                    "--output-dir",
                    temp_dir,
                ],
                cwd=ROOT,
                env=self._base_env(),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(dry_run_completed.returncode, 0, msg=dry_run_completed.stderr)
            self.assertIn("Dry-run simulated 1 trial(s)", dry_run_completed.stdout)
            self.assertIn('"succeeded": 1', dry_run_completed.stdout)

            run_dir = Path(temp_dir) / "plan-mobile-agent-v3-5-minimal"
            self.assertTrue((run_dir / "manifest.json").exists())
            self.assertTrue((run_dir / "summary.json").exists())
            summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["counts"]["planned_trials"], 1)
            self.assertEqual(summary["counts"]["completed"], 1)
            self.assertEqual(summary["counts"]["failed"], 0)

    def test_run_command_executes_wrapped_mobile_agent_v3_5_pipeline_in_fake_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "mobile-agent-v3-5-run"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "snowl_mobile",
                    "run",
                    str(RUN_CONFIG),
                    "--device-mode",
                    "fake",
                    "--output-dir",
                    str(run_dir),
                ],
                cwd=ROOT,
                env=self._smoke_env(),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            self.assertIn("completed with 1 succeeded, 0 failed", completed.stdout)
            self.assertIn("device_mode='fake'", completed.stdout)

            summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["counts"]["planned_trials"], 1)
            self.assertEqual(summary["counts"]["completed"], 1)
            self.assertEqual(summary["counts"]["failed"], 0)
            self.assertEqual(summary["trials"][0]["execution_modes"], ["bridge_mock"])

            trial_dirs = list((run_dir / "trials").iterdir())
            self.assertEqual(len(trial_dirs), 1)
            trial_dir = trial_dirs[0]
            self.assertTrue((trial_dir / "trajectory.json").exists())
            self.assertTrue((trial_dir / "score.json").exists())
            self.assertTrue((trial_dir / "raw" / "mobile_agent_v3_5" / "wrapped_result.json").exists())
            self.assertTrue(
                (
                    trial_dir
                    / "raw"
                    / "mobile_agent_v3_5_mobilesafetybench"
                    / "bridge_request.json"
                ).exists()
            )
            summarize_completed = subprocess.run(
                [sys.executable, "-m", "snowl_mobile", "summarize", str(run_dir)],
                cwd=ROOT,
                env=self._base_env(),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(summarize_completed.returncode, 0, msg=summarize_completed.stderr)
            self.assertIn("Summary for run", summarize_completed.stdout)
            self.assertIn('"completed": 1', summarize_completed.stdout)

    def test_unified_run_config_plans_all_tasks_and_can_be_smoked_with_selector_override(self) -> None:
        plan_completed = subprocess.run(
            [sys.executable, "-m", "snowl_mobile", "plan", str(RUN_CONFIG)],
            cwd=ROOT,
            env=self._base_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(plan_completed.returncode, 0, msg=plan_completed.stderr)
        self.assertIn('"run_id": "plan-mobile_agent_v3_5__mobilesafetybench"', plan_completed.stdout)
        self.assertIn('"planned_trials": 250', plan_completed.stdout)
        self.assertIn('"agent_id": "mobile_agent_v3_5"', plan_completed.stdout)
        self.assertIn('"bridge_id": "mobile_agent_v3_5__mobilesafetybench"', plan_completed.stdout)

        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "mobile-agent-v3-5-full-smoke"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "snowl_mobile",
                    "run",
                    str(RUN_CONFIG),
                    "--device-mode",
                    "fake",
                    "--output-dir",
                    str(run_dir),
                ],
                cwd=ROOT,
                env=self._smoke_env(),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            self.assertIn("completed with 1 succeeded, 0 failed", completed.stdout)
            self.assertIn("device_mode='fake'", completed.stdout)

            summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["counts"]["planned_trials"], 1)
            self.assertEqual(summary["counts"]["completed"], 1)
            self.assertEqual(summary["counts"]["failed"], 0)
            self.assertEqual(summary["trials"][0]["execution_modes"], ["bridge_mock"])


if __name__ == "__main__":
    unittest.main()
