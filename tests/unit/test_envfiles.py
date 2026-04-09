from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from snowl_mobile.utils.envfiles import autoload_local_env_files


class EnvFileSupportTestCase(unittest.TestCase):
    def test_autoload_local_env_files_loads_dot_env_local(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {}, clear=False):
            cwd = Path(temp_dir)
            (cwd / ".env.local").write_text(
                "PHONE_AGENT_MODEL=Qwen/Qwen3-VL-235B-A22B-Instruct\n",
                encoding="utf-8",
            )
            loaded = autoload_local_env_files(cwd)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(os.environ["PHONE_AGENT_MODEL"], "Qwen/Qwen3-VL-235B-A22B-Instruct")


if __name__ == "__main__":
    unittest.main()
