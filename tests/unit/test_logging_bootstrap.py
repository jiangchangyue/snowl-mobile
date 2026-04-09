from __future__ import annotations

import logging
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from snowl_mobile.core.logging import configure_logging, get_trial_logger


class LoggingBootstrapTestCase(unittest.TestCase):
    def test_run_log_records_info_even_when_console_verbosity_is_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_log = Path(temp_dir) / "run.log"

            configure_logging(verbosity=0, log_file=run_log)
            logging.getLogger("snowl_mobile.test").info("default-file-log-line")
            logging.shutdown()

            self.assertIn("default-file-log-line", run_log.read_text(encoding="utf-8"))

    def test_run_and_trial_logs_are_written(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_log = Path(temp_dir) / "run.log"
            trial_log = Path(temp_dir) / "trial.log"

            configure_logging(verbosity=1, log_file=run_log)
            logging.getLogger("snowl_mobile.test").info("run-log-line")

            trial_logger = get_trial_logger("trial-001", trial_log)
            trial_logger.info("trial-log-line")
            logging.shutdown()

            self.assertIn("run-log-line", run_log.read_text(encoding="utf-8"))
            self.assertIn("trial-log-line", trial_log.read_text(encoding="utf-8"))
            self.assertNotIn("trial-log-line", run_log.read_text(encoding="utf-8"))
