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
CONFIG = ROOT / "configs" / "runs" / "autoglm_androidworld.yml"


class OpenAutoGLMAndroidWorldCLITestCase(unittest.TestCase):
    def _base_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC)
        return env

    def _smoke_env(self) -> dict[str, str]:
        env = self._base_env()
        env["SNOWL_ANDROIDWORLD_SUITE_FAMILY"] = "android"
        env["SNOWL_ANDROIDWORLD_TASKS"] = "SimpleSmsSend"
        return env

    def test_validate_plan_run_and_summarize_work_for_fake_androidworld_pair(self) -> None:
        validate_completed = subprocess.run(
            [sys.executable, "-m", "snowl_mobile", "validate-config", str(CONFIG)],
            cwd=ROOT,
            env=self._smoke_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(validate_completed.returncode, 0, msg=validate_completed.stderr)
        self.assertIn('"bridge_id": "open_autoglm__androidworld"', validate_completed.stdout)
        self.assertIn('"benchmark_id": "androidworld"', validate_completed.stdout)

        plan_completed = subprocess.run(
            [sys.executable, "-m", "snowl_mobile", "plan", str(CONFIG)],
            cwd=ROOT,
            env=self._smoke_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(plan_completed.returncode, 0, msg=plan_completed.stderr)
        self.assertIn('"agent_id": "open_autoglm"', plan_completed.stdout)
        self.assertIn('"benchmark_id": "androidworld"', plan_completed.stdout)
        self.assertIn('"planned_trials": 1', plan_completed.stdout)

        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "autoglm-androidworld-fake"
            run_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "snowl_mobile",
                    "run",
                    str(CONFIG),
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
            self.assertEqual(run_completed.returncode, 0, msg=run_completed.stderr)
            self.assertIn("[run] Task 1/1 started:", run_completed.stdout)
            self.assertIn("[run] instruction:", run_completed.stdout)
            self.assertIn("[run] Task 1/1 finished:", run_completed.stdout)
            self.assertIn("completed with 1 succeeded, 0 failed", run_completed.stdout)
            self.assertIn("device_mode='fake'", run_completed.stdout)

            self.assertTrue((run_dir / "summary.json").exists())
            summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["counts"]["planned_trials"], 1)
            self.assertEqual(summary["counts"]["completed"], 1)
            self.assertEqual(summary["counts"]["failed"], 0)
            self.assertIn("Open-AutoGLM x AndroidWorld", "\n".join(summary.get("notes", [])))

            trial_dirs = sorted((run_dir / "trials").iterdir())
            self.assertEqual(len(trial_dirs), 1)
            self.assertTrue((trial_dirs[0] / "score.json").exists())
            self.assertTrue((trial_dirs[0] / "trajectory.json").exists())
            self.assertTrue((trial_dirs[0] / "raw" / "open_autoglm_androidworld" / "bridge_request.json").exists())
            self.assertTrue((trial_dirs[0] / "raw" / "open_autoglm_androidworld" / "final_result.json").exists())

            summarize_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "snowl_mobile",
                    "summarize",
                    str(run_dir),
                ],
                cwd=ROOT,
                env=self._smoke_env(),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(summarize_completed.returncode, 0, msg=summarize_completed.stderr)
            self.assertIn('"planned_trials": 1', summarize_completed.stdout)
            self.assertIn('"completed": 1', summarize_completed.stdout)

    def test_validate_and_plan_work_for_full_androidworld_config(self) -> None:
        validate_completed = subprocess.run(
            [sys.executable, "-m", "snowl_mobile", "validate-config", str(CONFIG)],
            cwd=ROOT,
            env=self._base_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(validate_completed.returncode, 0, msg=validate_completed.stderr)
        self.assertIn('"run_name": "open_autoglm__androidworld"', validate_completed.stdout)
        self.assertIn('"suite_family": "android_world"', validate_completed.stdout)

        plan_completed = subprocess.run(
            [sys.executable, "-m", "snowl_mobile", "plan", str(CONFIG)],
            cwd=ROOT,
            env=self._base_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(plan_completed.returncode, 0, msg=plan_completed.stderr)
        self.assertIn('"bridge_id": "open_autoglm__androidworld"', plan_completed.stdout)
        self.assertIn('"pair_recipe_id": "open_autoglm_androidworld_existing_device"', plan_completed.stdout)

        payload = json.loads(plan_completed.stdout[plan_completed.stdout.index("{"):])
        self.assertGreaterEqual(payload["matrix"]["planned_trials"], 100)
        self.assertEqual(payload["matrix"]["incompatible_combinations"], 0)

    def test_fake_full_run_and_summarize_persist_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "autoglm-androidworld-full-fake"
            run_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "snowl_mobile",
                    "run",
                    str(CONFIG),
                    "--device-mode",
                    "fake",
                    "--output-dir",
                    str(run_dir),
                ],
                cwd=ROOT,
                env=self._base_env(),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(run_completed.returncode, 0, msg=run_completed.stderr)
            self.assertIn("completed with", run_completed.stdout)
            self.assertIn("device_mode='fake'", run_completed.stdout)

            summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "COMPLETED")
            self.assertGreaterEqual(summary["counts"]["planned_trials"], 100)
            self.assertEqual(summary["counts"]["completed"], summary["counts"]["planned_trials"])

            trial_dirs = sorted((run_dir / "trials").iterdir())
            self.assertEqual(len(trial_dirs), summary["counts"]["planned_trials"])
            first_trial = trial_dirs[0]
            self.assertTrue((first_trial / "score.json").exists())
            self.assertTrue((first_trial / "trajectory.json").exists())
            self.assertTrue((first_trial / "trial.log").exists())
            self.assertTrue((first_trial / "raw" / "open_autoglm_androidworld" / "bridge_request.json").exists())
            self.assertTrue((first_trial / "raw" / "open_autoglm_androidworld" / "final_result.json").exists())

            summarize_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "snowl_mobile",
                    "summarize",
                    str(run_dir),
                ],
                cwd=ROOT,
                env=self._base_env(),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(summarize_completed.returncode, 0, msg=summarize_completed.stderr)
            self.assertIn(f'"planned_trials": {summary["counts"]["planned_trials"]}', summarize_completed.stdout)
            self.assertIn(f'"completed": {summary["counts"]["completed"]}', summarize_completed.stdout)


if __name__ == "__main__":
    unittest.main()
