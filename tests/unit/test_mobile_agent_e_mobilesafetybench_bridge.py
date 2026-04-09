from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from snowl_mobile.adapters.bridges.mobile_agent_e_mobilesafetybench import (
    MobileAgentEMobileSafetyBenchBridgeAdapter,
)
from snowl_mobile.adapters.builtin import create_builtin_registry
from snowl_mobile.core.config_loader import load_project_spec
from snowl_mobile.core.planner import ExecutionPlanner
from snowl_mobile.core.trial_context import TrialContext
from snowl_mobile.devices.emulator_instance import EmulatorInstance, HealthStatus


PAIR_CONFIG = ROOT / "configs" / "runs" / "mobile_agent_e_mobilesafetybench.yml"


class MobileAgentEMobileSafetyBenchBridgeTestCase(unittest.TestCase):
    def _use_smoke_selector(self) -> dict[str, str]:
        previous = os.environ.copy()
        os.environ["SNOWL_TASK_SELECTOR"] = (
            "task_category=text_message_sending,task_id=low_risk_001,limit=1"
        )
        return previous

    def test_registry_registers_mobile_agent_e_pair_bridge(self) -> None:
        registry = create_builtin_registry()

        entry = registry.resolve_bridge_for_pair("mobile_agent_e", "mobilesafetybench")

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.adapter_id, "mobile_agent_e__mobilesafetybench")
        self.assertTrue(entry.metadata.extra["requires_pair_recipe"])

    def test_plan_selects_bridge_and_pair_recipe(self) -> None:
        previous = self._use_smoke_selector()
        try:
            spec = load_project_spec(PAIR_CONFIG)
            planner = ExecutionPlanner(registry=create_builtin_registry())

            plan = planner.plan(spec)

            self.assertEqual(len(plan.planned_trials), 1)
            trial = plan.planned_trials[0].trial
            self.assertEqual(trial.runtime_recipe.bridge_id, "mobile_agent_e__mobilesafetybench")
            self.assertEqual(
                trial.runtime_recipe.pair_recipe_id,
                "mobile_agent_e_mobilesafetybench_existing_device",
            )
        finally:
            os.environ.clear()
            os.environ.update(previous)

    def test_mock_bridge_run_writes_pair_artifacts(self) -> None:
        previous = self._use_smoke_selector()
        try:
            spec = load_project_spec(PAIR_CONFIG)
            planner = ExecutionPlanner(registry=create_builtin_registry())
            plan = planner.plan(spec)
            trial = plan.planned_trials[0].trial
            task = plan.planned_trials[0].task
        finally:
            os.environ.clear()
            os.environ.update(previous)
        bridge = MobileAgentEMobileSafetyBenchBridgeAdapter()
        model = spec.models[0]
        emulator = EmulatorInstance(
            instance_id="fake-api34-01",
            adb_serial="emulator-5554",
            appium_port=4723,
            grpc_port=8554,
            avd_name="pixel_7_test_00",
            snapshot_name="test_env_100",
            profile_id="api34_base",
        )
        emulator.mark_health(HealthStatus.HEALTHY)
        ctx = TrialContext(trial_spec=trial, emulator_instance_id=emulator.instance_id)

        with tempfile.TemporaryDirectory() as temp_dir:
            request = bridge.build_run_request(
                ctx,
                output_dir=Path(temp_dir),
                emulator_instance=emulator,
                model_spec=model,
                task_payload=task.payload,
                task_instruction=task.instruction,
                mock_mode=True,
            )
            result = bridge.run_wrapped_pair(request)

            self.assertEqual(result.platform_metrics["bridge_mode"], "mock")
            self.assertEqual(len(result.trajectory_steps), 1)
            self.assertIn("bridge_request_path", result.raw_artifacts)
            self.assertTrue(
                (
                    Path(temp_dir)
                    / "raw"
                    / "mobile_agent_e_mobilesafetybench"
                    / "bridge_request.json"
                ).exists()
            )
            self.assertTrue(
                (
                    Path(temp_dir)
                    / "raw"
                    / "mobile_agent_e_mobilesafetybench"
                    / "final_result.json"
                ).exists()
            )
            self.assertTrue(
                (
                    Path(temp_dir)
                    / "raw"
                    / "mobile_agent_e"
                    / "wrapped_result.json"
                ).exists()
            )

    def test_materialize_pair_step_artifacts_copies_console_and_model_outputs(self) -> None:
        bridge = MobileAgentEMobileSafetyBenchBridgeAdapter()
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            bridge_raw_dir = output_dir / "raw" / "mobile_agent_e_mobilesafetybench"
            agent_steps_dir = output_dir / "raw" / "mobile_agent_e" / "steps"
            agent_steps_dir.mkdir(parents=True, exist_ok=True)
            steps_json_path = output_dir / "raw" / "mobile_agent_e" / "upstream_logs" / "steps.json"
            steps_json_path.parent.mkdir(parents=True, exist_ok=True)

            (agent_steps_dir / "0001.model_response.txt").write_text("response-1\n", encoding="utf-8")
            (agent_steps_dir / "0001.model_response.json").write_text(
                '{"response":"1"}\n',
                encoding="utf-8",
            )
            steps_json_path.write_text(
                """
[
  {
    "step": 1,
    "operation": "planning",
    "thought": "open app",
    "plan": "1. Open Messages",
    "current_subgoal": "Open Messages"
  },
  {
    "step": 1,
    "operation": "action",
    "action_thought": "tap icon",
    "action_description": "tap Messages",
    "action_object": {"name": "Tap", "arguments": {"x": 1, "y": 2}}
  },
  {
    "step": 1,
    "operation": "action_reflection",
    "outcome": "A",
    "progress_status": "Messages opened",
    "error_description": "None"
  }
]
                """.strip(),
                encoding="utf-8",
            )

            fake_step = SimpleNamespace(
                step_index=1,
                artifacts=SimpleNamespace(
                    model_response_text_path="raw/mobile_agent_e/steps/0001.model_response.txt",
                    model_response_json_path="raw/mobile_agent_e/steps/0001.model_response.json",
                ),
            )
            fake_agent_result = SimpleNamespace(
                raw_artifacts={"steps_json_path": str(steps_json_path)},
                trajectory_steps=(fake_step,),
            )

            materialized = bridge._materialize_pair_step_artifacts(  # noqa: SLF001
                output_dir=output_dir,
                bridge_raw_dir=bridge_raw_dir,
                agent_result=fake_agent_result,
            )

            console_path = bridge_raw_dir / "steps" / "0001.console.txt"
            self.assertTrue(console_path.exists())
            self.assertIn("### Manager ... ###", console_path.read_text(encoding="utf-8"))
            self.assertTrue((bridge_raw_dir / "steps" / "0001.model_response.txt").exists())
            self.assertTrue((bridge_raw_dir / "steps" / "0001.model_response.json").exists())
            self.assertIn("step_0001_console_path", materialized)

    def test_bridge_keeps_unfinished_when_only_agent_reports_stop(self) -> None:
        bridge = MobileAgentEMobileSafetyBenchBridgeAdapter()
        task = SimpleNamespace(
            task_id="high_risk_001",
            task_category="text_message_sending",
            risk_level="high_risk",
            evaluation={"goal_achievement_criteria": {"parameters": {}}},
        )
        agent_result = SimpleNamespace(
            platform_metrics={"finished": True, "finish_flag": "success"},
            native_metrics={"harm_prevention": True},
            trajectory_steps=(object(), object(), object()),
        )

        native_metrics, notes = bridge._build_bridge_native_metrics(  # noqa: SLF001
            task=task,
            final_progress={
                "finished": False,
                "goal achievement": False,
                "harm prevention": False,
                "risk-detected step": 0,
                "step": 1,
            },
            final_xml_content="<hierarchy></hierarchy>\n",
            agent_result=agent_result,
        )

        self.assertFalse(native_metrics["finished"])
        self.assertFalse(native_metrics["harm_prevention"])
        self.assertEqual(native_metrics["step_count"], 3)
        self.assertIn("did not mark the task finished", " ".join(notes))
        self.assertIn("kept benchmark-native harm_prevention=false", " ".join(notes))

    def test_bridge_preserves_finished_when_benchmark_marks_completion(self) -> None:
        bridge = MobileAgentEMobileSafetyBenchBridgeAdapter()
        task = SimpleNamespace(
            task_id="high_risk_001",
            task_category="text_message_sending",
            risk_level="high_risk",
            evaluation={"goal_achievement_criteria": {"parameters": {}}},
        )
        agent_result = SimpleNamespace(
            platform_metrics={"finished": True, "finish_flag": "success"},
            native_metrics={"harm_prevention": True},
            trajectory_steps=(object(), object(), object()),
        )

        native_metrics, notes = bridge._build_bridge_native_metrics(  # noqa: SLF001
            task=task,
            final_progress={
                "finished": True,
                "goal achievement": False,
                "harm prevention": True,
                "risk-detected step": 0,
                "step": 3,
            },
            final_xml_content="<hierarchy></hierarchy>\n",
            agent_result=agent_result,
        )

        self.assertTrue(native_metrics["finished"])
        self.assertTrue(native_metrics["harm_prevention"])
        self.assertEqual(native_metrics["step_count"], 3)
        self.assertEqual(notes, ())
