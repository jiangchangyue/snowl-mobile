from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from snowl_mobile.adapters.builtin import create_builtin_registry


class RegistryTestCase(unittest.TestCase):
    def test_builtin_registry_registers_stub_adapters(self) -> None:
        registry = create_builtin_registry()
        summary = registry.summary()
        self.assertEqual(
            summary["agents"],
            ["dummy_text_agent", "dummy_vision_agent", "mobile_agent_e", "mobile_agent_v3_5", "open_autoglm"],
        )
        self.assertEqual(summary["benchmarks"], ["androidworld", "dummy_benchmark", "mobilesafetybench"])
        self.assertEqual(
            summary["bridges"],
            [
                "dummy_vision__dummy_benchmark",
                "mobile_agent_e__androidworld",
                "mobile_agent_e__mobilesafetybench",
                "mobile_agent_v3_5__androidworld",
                "mobile_agent_v3_5__mobilesafetybench",
                "open_autoglm__androidworld",
                "open_autoglm__mobilesafetybench",
            ],
        )

    def test_registry_query_filters_by_metadata(self) -> None:
        registry = create_builtin_registry()
        vision_agents = registry.query("agent", modality="image")
        wrap_benchmarks = registry.query("benchmark", integration_mode="wrap")
        hybrid_benchmarks = registry.query("benchmark", integration_mode="hybrid")

        self.assertEqual(
            [entry.adapter_id for entry in vision_agents],
            ["dummy_vision_agent", "mobile_agent_e", "mobile_agent_v3_5", "open_autoglm"],
        )
        self.assertEqual([entry.adapter_id for entry in wrap_benchmarks], ["dummy_benchmark"])
        self.assertEqual([entry.adapter_id for entry in hybrid_benchmarks], ["androidworld", "mobilesafetybench"])

    def test_registry_resolves_bridge_by_pair(self) -> None:
        registry = create_builtin_registry()
        entry = registry.resolve_bridge_for_pair("dummy_vision_agent", "dummy_benchmark")
        mobile_agent_e_androidworld_entry = registry.resolve_bridge_for_pair("mobile_agent_e", "androidworld")
        mobile_agent_e_entry = registry.resolve_bridge_for_pair("mobile_agent_e", "mobilesafetybench")
        mobile_agent_v35_androidworld_entry = registry.resolve_bridge_for_pair("mobile_agent_v3_5", "androidworld")
        mobile_agent_v35_entry = registry.resolve_bridge_for_pair("mobile_agent_v3_5", "mobilesafetybench")
        androidworld_entry = registry.resolve_bridge_for_pair("open_autoglm", "androidworld")
        real_pair_entry = registry.resolve_bridge_for_pair("open_autoglm", "mobilesafetybench")

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.adapter_id, "dummy_vision__dummy_benchmark")
        self.assertIsNotNone(mobile_agent_e_androidworld_entry)
        assert mobile_agent_e_androidworld_entry is not None
        self.assertEqual(mobile_agent_e_androidworld_entry.adapter_id, "mobile_agent_e__androidworld")
        self.assertIsNotNone(mobile_agent_e_entry)
        assert mobile_agent_e_entry is not None
        self.assertEqual(mobile_agent_e_entry.adapter_id, "mobile_agent_e__mobilesafetybench")
        self.assertIsNotNone(mobile_agent_v35_androidworld_entry)
        assert mobile_agent_v35_androidworld_entry is not None
        self.assertEqual(mobile_agent_v35_androidworld_entry.adapter_id, "mobile_agent_v3_5__androidworld")
        self.assertIsNotNone(mobile_agent_v35_entry)
        assert mobile_agent_v35_entry is not None
        self.assertEqual(mobile_agent_v35_entry.adapter_id, "mobile_agent_v3_5__mobilesafetybench")
        self.assertIsNotNone(androidworld_entry)
        assert androidworld_entry is not None
        self.assertEqual(androidworld_entry.adapter_id, "open_autoglm__androidworld")
        self.assertIsNotNone(real_pair_entry)
        assert real_pair_entry is not None
        self.assertEqual(real_pair_entry.adapter_id, "open_autoglm__mobilesafetybench")
