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
from snowl_mobile.core.config_loader import load_project_spec
from snowl_mobile.core.planner import ExecutionPlanner


class PlannerTestCase(unittest.TestCase):
    def test_trial_id_skips_agent_and_benchmark_when_run_name_already_contains_pair(self) -> None:
        planner = ExecutionPlanner(registry=create_builtin_registry())

        trial_id = planner._build_trial_id(
            "open_autoglm__mobilesafetybench",
            "open_autoglm",
            "mobilesafetybench",
            "seed-0001",
            "text_message_sending:high_risk_001",
        )

        self.assertEqual(
            trial_id,
            "open_autoglm__mobilesafetybench-text_message_sending-high_risk_001-seed-0001",
        )

    def test_plan_builds_trial_plan(self) -> None:
        planner = ExecutionPlanner(registry=create_builtin_registry())
        spec = load_project_spec(ROOT / "project.example.yml")
        plan = planner.plan(spec)

        self.assertEqual(len(plan.planned_trials), 4)
        self.assertEqual(len(plan.diagnostics), 0)
        self.assertEqual(plan.planned_trials[0].trial.status.value, "PENDING")
        self.assertEqual(plan.planned_trials[0].task.task_id, "dummy-task-001")
        self.assertEqual(plan.planned_trials[1].task.task_id, "dummy-task-002")
        vision_trials = [
            entry for entry in plan.planned_trials if entry.trial.agent_id == "dummy_vision_agent"
        ]
        self.assertEqual(len(vision_trials), 2)
        self.assertTrue(all(entry.trial.runtime_recipe.bridge_id == "dummy_vision__dummy_benchmark" for entry in vision_trials))
        self.assertTrue(all(entry.trial.runtime_recipe.pair_recipe_id == "dummy_vision_bridge_recipe" for entry in vision_trials))

    def test_dry_run_simulates_retry_then_completion(self) -> None:
        planner = ExecutionPlanner(registry=create_builtin_registry())
        spec = load_project_spec(ROOT / "project.example.yml")
        result = planner.dry_run(spec)

        self.assertEqual(result.scheduler_snapshot.succeeded, 4)
        self.assertEqual(result.scheduler_snapshot.failed, 0)
        vision_trials = [
            trial_state for trial_state in result.trial_states if trial_state.spec.agent_id == "dummy_vision_agent"
        ]
        self.assertEqual(len(vision_trials), 2)
        self.assertTrue(all(trial_state.attempt_count == 2 for trial_state in vision_trials))
        self.assertTrue(all(trial_state.status.value == "COMPLETED" for trial_state in vision_trials))

    def test_plan_records_pair_recipe_requirement_when_bridge_cannot_activate(self) -> None:
        planner = ExecutionPlanner(registry=create_builtin_registry())
        spec = load_project_spec(ROOT / "project.example.yml")
        benchmark = replace(
            spec.benchmarks[0],
            supported_agent_ids=("dummy_text_agent",),
        )
        mutated_spec = replace(
            spec,
            benchmarks=(benchmark,),
            pair_runtime_recipes=(),
        )

        plan = planner.plan(mutated_spec)

        self.assertEqual(len(plan.planned_trials), 2)
        self.assertEqual(len(plan.diagnostics), 2)
        self.assertTrue(
            any(
                "requires a pair-specific runtime recipe" in issue
                for diagnostic in plan.diagnostics
                for issue in diagnostic.issues
            )
        )
