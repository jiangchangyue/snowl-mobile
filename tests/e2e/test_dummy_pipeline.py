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


class DummyPipelineE2ETestCase(unittest.TestCase):
    def _base_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC)
        return env

    def test_run_then_summarize_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "dummy-e2e-run"
            run_completed = subprocess.run(
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
            self.assertEqual(run_completed.returncode, 0, msg=run_completed.stderr)

            summary_path = run_dir / "summary.json"
            manifest_path = run_dir / "manifest.json"
            trials_dir = run_dir / "trials"
            self.assertTrue(summary_path.exists())
            self.assertTrue(manifest_path.exists())
            self.assertEqual(len([path for path in trials_dir.iterdir() if path.is_dir()]), 4)

            summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary_payload["counts"]["planned_trials"], 4)
            self.assertEqual(summary_payload["counts"]["completed"], 4)
            self.assertEqual(summary_payload["counts"]["failed"], 0)
            self.assertIn("metrics_summary", summary_payload)

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
            self.assertIn("Summary for run", summarize_completed.stdout)
            self.assertIn('"success_rate": 1.0', summarize_completed.stdout)
            self.assertIn('"planned_trials": 4', summarize_completed.stdout)
