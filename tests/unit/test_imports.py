from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class ImportTestCase(unittest.TestCase):
    def test_core_modules_import(self) -> None:
        import snowl_mobile
        from snowl_mobile.adapters.agents.base import BaseAgentAdapter
        from snowl_mobile.core.agent_spec import AgentSpec
        from snowl_mobile.core.benchmark_spec import BenchmarkSpec
        from snowl_mobile.cli.main import build_parser
        from snowl_mobile.core.config_loader import load_project_spec
        from snowl_mobile.core.compatibility import CompatibilityResolver
        from snowl_mobile.core.registry import Registry

        self.assertTrue(hasattr(snowl_mobile, "__version__"))
        self.assertTrue(hasattr(BaseAgentAdapter, "metadata"))
        self.assertTrue(hasattr(AgentSpec, "from_mapping"))
        self.assertTrue(hasattr(BenchmarkSpec, "from_mapping"))
        self.assertTrue(hasattr(CompatibilityResolver, "check_agent_model"))
        self.assertIsNotNone(build_parser())
        self.assertTrue(callable(load_project_spec))
        self.assertIsInstance(Registry().summary(), dict)
