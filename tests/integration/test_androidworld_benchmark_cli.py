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
CONFIG = ROOT / "configs" / "runs" / "androidworld_benchmark.yml"


class AndroidWorldBenchmarkCLITestCase(unittest.TestCase):
    def _base_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC)
        return env

    def test_benchmark_setup_and_benchmark_run_work_in_fake_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            setup_dir = Path(temp_dir) / "setup-run"
            setup_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "snowl_mobile",
                    "benchmark-setup",
                    str(CONFIG),
                    "--output-dir",
                    str(setup_dir),
                ],
                cwd=ROOT,
                env=self._base_env(),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(setup_completed.returncode, 0, msg=setup_completed.stderr)
            self.assertIn("Benchmark setup", setup_completed.stdout)
            self.assertTrue((setup_dir / "summary.json").exists())
            setup_summary = json.loads((setup_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(setup_summary["counts"]["completed"], 1)
            self.assertEqual(setup_summary["counts"]["failed"], 0)

            trial_dirs = sorted((setup_dir / "trials").iterdir())
            self.assertEqual(len(trial_dirs), 1)
            self.assertTrue((trial_dirs[0] / "raw" / "androidworld" / "setup.result.json").exists())

            run_dir = Path(temp_dir) / "benchmark-run"
            run_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "snowl_mobile",
                    "benchmark-run",
                    str(CONFIG),
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
            self.assertIn("Benchmark-side run", run_completed.stdout)
            self.assertTrue((run_dir / "summary.json").exists())
            run_summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(run_summary["counts"]["completed"], 1)
            self.assertEqual(run_summary["counts"]["failed"], 0)
            self.assertIn("benchmark-side platform probe path", "\n".join(run_summary.get("notes", [])))

            run_trial_dirs = sorted((run_dir / "trials").iterdir())
            self.assertEqual(len(run_trial_dirs), 1)
            self.assertTrue((run_trial_dirs[0] / "score.json").exists())
            self.assertTrue((run_trial_dirs[0] / "raw" / "androidworld" / "probe.result.json").exists())


if __name__ == "__main__":
    unittest.main()
