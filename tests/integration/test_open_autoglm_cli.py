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
CONFIG = ROOT / "configs" / "integrations" / "autoglm" / "minimal.yml"
REPO = ROOT / "references" / "agents" / "Open-AutoGLM"


class OpenAutoGLMCLITestCase(unittest.TestCase):
    def _base_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC)
        return env

    def test_inspect_repo_command_reports_open_autoglm(self) -> None:
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
        self.assertIn('"repo_name": "Open-AutoGLM"', completed.stdout)
        self.assertIn('"suggested_integration_mode": "hybrid"', completed.stdout)
        self.assertIn('"phone_agent/model/client.py"', completed.stdout)
        self.assertIn('"phone_agent/actions/handler.py"', completed.stdout)

    def test_validate_plan_and_dry_run_work_with_open_autoglm_config(self) -> None:
        validate_completed = subprocess.run(
            [sys.executable, "-m", "snowl_mobile", "validate-config", str(CONFIG)],
            cwd=ROOT,
            env=self._base_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(validate_completed.returncode, 0, msg=validate_completed.stderr)
        self.assertIn('"agent_id": "open_autoglm"', validate_completed.stdout)
        self.assertIn('"supported_backends": [', validate_completed.stdout)

        plan_completed = subprocess.run(
            [sys.executable, "-m", "snowl_mobile", "plan", str(CONFIG)],
            cwd=ROOT,
            env=self._base_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(plan_completed.returncode, 0, msg=plan_completed.stderr)
        self.assertIn('"agent_id": "open_autoglm"', plan_completed.stdout)
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

            run_dir = Path(temp_dir) / "plan-open-autoglm-minimal"
            self.assertTrue((run_dir / "manifest.json").exists())
            self.assertTrue((run_dir / "summary.json").exists())
            summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["counts"]["planned_trials"], 1)
            self.assertEqual(summary["counts"]["completed"], 1)
            self.assertEqual(summary["counts"]["failed"], 0)


if __name__ == "__main__":
    unittest.main()
