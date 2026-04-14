from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from snowl_mobile.adapters.builtin import create_builtin_registry
from snowl_mobile.core.compatibility import CompatibilityResolver
from snowl_mobile.core.config_loader import load_project_spec


class CompatibilityResolverTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = load_project_spec(ROOT / "project.example.yml")
        self.resolver = CompatibilityResolver(registry=create_builtin_registry())

    def test_agent_model_incompatibility_reports_missing_image_support(self) -> None:
        report = self.resolver.check_agent_model(self.spec.agents[1], self.spec.models[0])
        self.assertFalse(report.compatible)
        self.assertIn("missing required modalities: image", report.render())

    def test_agent_benchmark_incompatibility_reports_unsupported_agent(self) -> None:
        benchmark = replace(
            self.spec.benchmarks[0],
            supported_agent_ids=("dummy_vision_agent",),
        )
        report = self.resolver.check_agent_benchmark(self.spec.agents[0], benchmark)
        self.assertFalse(report.compatible)
        self.assertIn("does not list agent 'dummy_text_agent' as supported", report.render())

    def test_benchmark_runtime_incompatibility_reports_backend_mismatch(self) -> None:
        runtime_recipe = replace(
            self.spec.build_runtime_recipe(self.spec.agents[0], self.spec.benchmarks[0]),
            control_backend="uiautomator",
            backend_requirements=("uiautomator",),
        )
        report = self.resolver.check_benchmark_runtime(self.spec.benchmarks[0], runtime_recipe)
        self.assertFalse(report.compatible)
        self.assertIn("control_backend 'uiautomator'", report.render())

    def test_agent_benchmark_incompatibility_can_be_resolved_via_bridge(self) -> None:
        benchmark = replace(
            self.spec.benchmarks[0],
            supported_agent_ids=("dummy_text_agent",),
        )
        runtime_recipe = self.spec.build_runtime_recipe(self.spec.agents[1], self.spec.benchmarks[0])
        report = self.resolver.check_agent_benchmark(self.spec.agents[1], benchmark, runtime_recipe)

        self.assertTrue(report.compatible)
        self.assertEqual(report.bridge_id, "dummy_vision__dummy_benchmark")
        self.assertIn("handled by bridge", report.render())

    def test_bridge_reports_missing_pair_recipe_when_required(self) -> None:
        benchmark = replace(
            self.spec.benchmarks[0],
            supported_agent_ids=("dummy_text_agent",),
        )
        runtime_recipe = replace(
            self.spec.build_runtime_recipe(self.spec.agents[1], self.spec.benchmarks[0]),
            bridge_id="",
            pair_recipe_id="",
            pair_requires_bridge=False,
            ports={},
            launch_hints={},
        )
        report = self.resolver.check_agent_benchmark(self.spec.agents[1], benchmark, runtime_recipe)

        self.assertFalse(report.compatible)
        self.assertIn("requires a pair-specific runtime recipe", report.render())
