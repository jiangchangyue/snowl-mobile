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
CONFIG = ROOT / "configs" / "runs" / "autoglm_mobilesafetybench.yml"
REPO = ROOT / "references" / "benchmarks" / "mobilesafetybench"


class MobileSafetyBenchCLITestCase(unittest.TestCase):
    def _base_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC)
        return env

    def test_inspect_repo_command_reports_mobilesafetybench(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "snowl_mobile",
                "inspect-repo",
                "benchmark",
                str(REPO),
            ],
            cwd=ROOT,
            env=self._base_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertIn('"repo_name": "mobilesafetybench"', completed.stdout)
        self.assertIn('"suggested_integration_mode": "wrap"', completed.stdout)
        self.assertIn('"task_discovery_candidates": [', completed.stdout)

    def _smoke_env(self) -> dict[str, str]:
        env = self._base_env()
        env["SNOWL_TASK_SELECTOR"] = "task_category=text_message_sending,task_id=high_risk_001,limit=1"
        return env

    def test_plan_and_dry_run_work_with_mobilesafetybench_config(self) -> None:
        plan_completed = subprocess.run(
            [sys.executable, "-m", "snowl_mobile", "plan", str(CONFIG)],
            cwd=ROOT,
            env=self._smoke_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(plan_completed.returncode, 0, msg=plan_completed.stderr)
        self.assertIn('"benchmark_id": "mobilesafetybench"', plan_completed.stdout)
        self.assertIn('"planned_trials": 1', plan_completed.stdout)
        self.assertIn('"task_id": "text_message_sending:high_risk_001"', plan_completed.stdout)

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
                env=self._smoke_env(),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(dry_run_completed.returncode, 0, msg=dry_run_completed.stderr)
            self.assertIn("Dry-run simulated 1 trial(s)", dry_run_completed.stdout)
            self.assertIn('"succeeded": 1', dry_run_completed.stdout)

            run_dir = Path(temp_dir) / "plan-open_autoglm__mobilesafetybench"
            self.assertTrue((run_dir / "manifest.json").exists())
            self.assertTrue((run_dir / "summary.json").exists())
            summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["counts"]["planned_trials"], 1)
            self.assertEqual(summary["counts"]["completed"], 1)
            self.assertEqual(summary["counts"]["failed"], 0)


if __name__ == "__main__":
    unittest.main()
