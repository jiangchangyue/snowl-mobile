from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from snowl_mobile.core.errors import ConfigError
from snowl_mobile.core.pair_runtime_recipe import PairRuntimeRecipeSpec
from snowl_mobile.integration.bridge_scaffold import (
    BridgePackageScaffoldGenerator,
    BridgePackageScaffoldRequest,
)


class BridgeSupportTestCase(unittest.TestCase):
    def test_pair_runtime_recipe_requires_bridge_id_when_flagged(self) -> None:
        with self.assertRaises(ConfigError):
            PairRuntimeRecipeSpec.from_mapping(
                {
                    "recipe_id": "broken_pair",
                    "agent_id": "agent-a",
                    "benchmark_id": "benchmark-a",
                    "requires_bridge": True,
                },
                "pair_runtime_recipes[0]",
            )

    def test_bridge_scaffold_generator_writes_package_layout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = BridgePackageScaffoldGenerator().generate(
                BridgePackageScaffoldRequest(
                    bridge_id="dummy_vision__dummy_benchmark",
                    agent_id="dummy_vision_agent",
                    benchmark_id="dummy_benchmark",
                    output_dir=Path(temp_dir),
                    integration_mode="hybrid",
                    requires_pair_recipe=True,
                )
            )

            self.assertTrue((result.scaffold_root / "bridge.py").exists())
            self.assertTrue((result.scaffold_root / "register.py").exists())
            self.assertTrue((result.scaffold_root / "pair_runtime_recipe.example.yml").exists())
            self.assertTrue((result.scaffold_root / "README.md").exists())
            self.assertTrue((result.scaffold_root / "contract.json").exists())
            self.assertTrue(
                (
                    result.scaffold_root
                    / "tests"
                    / "test_dummy_vision__dummy_benchmark_bridge.py"
                ).exists()
            )
            contract_payload = json.loads((result.scaffold_root / "contract.json").read_text(encoding="utf-8"))
            self.assertEqual(contract_payload["bridge_id"], "dummy_vision__dummy_benchmark")
            self.assertTrue(contract_payload["requires_pair_recipe"])
