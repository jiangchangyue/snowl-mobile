from __future__ import annotations

import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from snowl_mobile.adapters.builtin import create_builtin_registry
from snowl_mobile.artifacts.store import ArtifactStore
from snowl_mobile.artifacts.trajectory import (
    TrajectoryArtifacts,
    TrajectoryStep,
    TrajectoryTimestamps,
)
from snowl_mobile.core.config_loader import load_project_spec
from snowl_mobile.core.enums import ArtifactLevel
from snowl_mobile.core.logging import configure_logging
from snowl_mobile.core.planner import ExecutionPlanner
from snowl_mobile.core.trial_state_machine import TrialStateMachine
from snowl_mobile.runtime.trial_orchestrator import TrialArtifactRecord, TrialExecutionSummary
from snowl_mobile.scoring.score_bundle import ScoreBundle
from snowl_mobile.schemas.action import ActionRecord
from snowl_mobile.schemas.observation import ObservationBundle


class ArtifactStoreTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = load_project_spec(ROOT / "project.example.yml")
        self.planner = ExecutionPlanner(registry=create_builtin_registry())
        self.result = self.planner.dry_run(self.spec)

    def _trial_dir(self, layout: object, trial_id: str) -> Path:
        return layout.trials_dir / trial_id

    def test_persist_simulated_run_writes_expected_run_and_trial_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore(output_root=Path(temp_dir))
            layout = store.initialize_run(
                spec=self.spec,
                project_source=ROOT / "project.example.yml",
                run_id=self.result.run_context.run_id,
                plan_payload=self.result.plan.to_summary(),
                summary_payload=store.build_summary_payload(self.result),
            )
            configure_logging(verbosity=1, log_file=layout.run_log_path)
            store.persist_simulated_run(
                layout=layout,
                spec=self.spec,
                plan=self.result.plan,
                result=self.result,
            )

            self.assertTrue(layout.manifest_path.exists())
            self.assertTrue(layout.plan_path.exists())
            self.assertTrue(layout.summary_path.exists())
            self.assertTrue(layout.events_path.exists())
            self.assertTrue(layout.run_log_path.exists())

            trial_dir = self._trial_dir(
                layout,
                "demo_run-dummy_text_agent-dummy_benchmark-dummy-task-001-seed-0001",
            )
            self.assertTrue((trial_dir / "meta.json").exists())
            self.assertTrue((trial_dir / "runtime_recipe.json").exists())
            self.assertTrue((trial_dir / "score.json").exists())
            self.assertTrue((trial_dir / "trajectory.json").exists())
            self.assertTrue((trial_dir / "trial.log").exists())
            self.assertTrue((trial_dir / "steps" / "0001" / "observation.json").exists())
            self.assertTrue((trial_dir / "steps" / "0001" / "action.json").exists())
            self.assertTrue((trial_dir / "steps" / "0001" / "screenshot.txt").exists())
            self.assertTrue((trial_dir / "steps" / "0001" / "hierarchy.xml").exists())

            trajectory_payload = json.loads((trial_dir / "trajectory.json").read_text(encoding="utf-8"))
            self.assertEqual(trajectory_payload["step_count"], 1)
            self.assertEqual(trajectory_payload["score_path"], "score.json")
            first_step = trajectory_payload["steps"][0]
            self.assertIn("thought", first_step)
            self.assertIn("action", first_step)
            self.assertIn("action_input", first_step)
            self.assertIn("observation", first_step)
            self.assertIn("artifacts", first_step)
            self.assertIn("visible_text", first_step["observation"])
            self.assertIn("key_ui_elements", first_step["observation"])
            self.assertEqual(first_step["step"], 1)

            events = [
                json.loads(line)
                for line in layout.events_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertTrue(any(event["event"] == "run_initialized" for event in events))
            self.assertTrue(any(event["event"] == "trial_status_transition" for event in events))

    def test_light_artifact_level_keeps_steps_directory_but_skips_step_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            light_spec = replace(
                self.spec,
                artifacts=replace(self.spec.artifacts, level=ArtifactLevel.LIGHT),
            )
            result = self.planner.dry_run(light_spec)
            store = ArtifactStore(output_root=Path(temp_dir))
            layout = store.initialize_run(
                spec=light_spec,
                project_source=ROOT / "project.example.yml",
                run_id=result.run_context.run_id,
                plan_payload=result.plan.to_summary(),
                summary_payload=store.build_summary_payload(result),
            )
            store.persist_simulated_run(
                layout=layout,
                spec=light_spec,
                plan=result.plan,
                result=result,
            )

            trial_dir = self._trial_dir(
                layout,
                "demo_run-dummy_text_agent-dummy_benchmark-dummy-task-001-seed-0001",
            )
            self.assertTrue((trial_dir / "steps").exists())
            self.assertFalse((trial_dir / "steps" / "0001" / "observation.json").exists())

            trajectory_payload = json.loads((trial_dir / "trajectory.json").read_text(encoding="utf-8"))
            payload = trajectory_payload["steps"][0]
            self.assertIsNone(payload["artifacts"]["screenshot_path"])
            self.assertIsNone(payload["artifacts"]["xml_path"])

    def test_persist_platform_trial_artifacts_writes_incremental_score_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore(output_root=Path(temp_dir))
            layout = store.initialize_run(
                spec=self.spec,
                project_source=ROOT / "project.example.yml",
                run_id="incremental-demo-run",
                plan_payload=self.result.plan.to_summary(),
                summary_payload={
                    "run_id": "incremental-demo-run",
                    "status": "RUNNING",
                    "counts": {
                        "planned_trials": 1,
                        "diagnostics": 0,
                        "completed": 0,
                        "failed": 0,
                        "retrying": 0,
                        "queued": 1,
                        "running": 0,
                        "skipped": 0,
                    },
                },
            )

            trial_spec = self.result.plan.planned_trials[0].trial
            state_machine = TrialStateMachine()
            trial_state = state_machine.initialize(trial_spec, max_attempts=1)
            state_machine.queue(trial_state)
            state_machine.start(trial_state)
            state_machine.complete(trial_state)

            score_bundle = ScoreBundle(
                native_metrics={"task_success": 1},
                primary_metric=1,
                platform_metrics={"duration_ms": 1234},
                notes=["incremental persist test"],
            )
            step = TrajectoryStep(
                step_index=1,
                attempt=1,
                status="completed",
                observation=ObservationBundle(
                    timestamp="2026-03-21T10:00:00+00:00",
                    screenshot_path="steps/0001.png",
                    xml_path="steps/0001.xml",
                    parsed_text="Messages inbox",
                    package_name="com.google.android.apps.messaging",
                    screen_size="1080x2400",
                    extra={"ui_summary": [{"label": "Anders conversation"}]},
                ),
                action=ActionRecord(
                    agent_raw_output='do(action="Tap", element=[300, 585])',
                    parsed_action={"_metadata": "do", "action": "Tap", "element": [300, 585]},
                    executed_action={"action_name": "Tap"},
                    execution_result={"status": "completed"},
                ),
                artifacts=TrajectoryArtifacts(
                    screenshot_path="steps/0001.png",
                    xml_path="steps/0001.xml",
                    model_response_text_path="raw/steps/0001.model_response.txt",
                    model_response_json_path="raw/steps/0001.model_response.json",
                ),
                timestamps=TrajectoryTimestamps(
                    observed_at="2026-03-21T10:00:00+00:00",
                    action_at="2026-03-21T10:00:01+00:00",
                    persisted_at="2026-03-21T10:00:02+00:00",
                ),
                task_instruction="Open Messages and tap Anders.",
                thought="Anders is visible in the conversation list.",
                action_text='do(action="Tap", element=[300, 585])',
            )
            summary = TrialExecutionSummary(
                trial_id=trial_state.trial_id,
                task_id=trial_state.spec.task_id,
                agent_id=trial_state.spec.agent_id,
                benchmark_id=trial_state.spec.benchmark_id,
                status=trial_state.status.value,
                attempt_count=trial_state.attempt_count,
                total_duration_ms=1234,
                worker_attempts=0,
                execution_modes=("bridge_real",),
                requested_modes=("in_process",),
                instance_ids=("emulator-5554",),
                reset_strategies=("restore_snapshot_then_seed",),
                benchmark_seed_requested=False,
                primary_metric=1,
                platform_metrics={"duration_ms": 1234},
            )
            artifact = TrialArtifactRecord(
                trial_id=trial_state.trial_id,
                score_bundle=score_bundle,
                trajectory_steps=(step,),
                raw_artifacts={"bridge_request_path": "raw/open_autoglm_mobilesafetybench/bridge_request.json"},
                notes=("incremental persist",),
            )

            store.persist_platform_trial_artifacts(
                layout=layout,
                spec=self.spec,
                trial_state=trial_state,
                trial_summary=summary,
                trial_artifact=artifact,
            )

            trial_dir = self._trial_dir(layout, trial_state.trial_id)
            self.assertTrue((trial_dir / "meta.json").exists())
            self.assertTrue((trial_dir / "runtime_recipe.json").exists())
            self.assertTrue((trial_dir / "score.json").exists())
            self.assertTrue((trial_dir / "trajectory.json").exists())
            self.assertTrue((trial_dir / "trial.log").exists())
            score_payload = json.loads((trial_dir / "score.json").read_text(encoding="utf-8"))
            self.assertEqual(score_payload["primary_metric"], 1)
            trajectory_payload = json.loads((trial_dir / "trajectory.json").read_text(encoding="utf-8"))
            self.assertEqual(trajectory_payload["step_count"], 1)
            self.assertEqual(trajectory_payload["steps"][0]["thought"], "Anders is visible in the conversation list.")

    def test_failed_platform_trial_with_failure_json_writes_empty_trajectory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore(output_root=Path(temp_dir))
            layout = store.initialize_run(
                spec=self.spec,
                project_source=ROOT / "project.example.yml",
                run_id="failed-platform-run",
                plan_payload=self.result.plan.to_summary(),
                summary_payload={
                    "run_id": "failed-platform-run",
                    "status": "FAILED",
                    "counts": {
                        "planned_trials": 1,
                        "diagnostics": 0,
                        "completed": 0,
                        "failed": 1,
                        "retrying": 0,
                        "queued": 0,
                        "running": 0,
                        "skipped": 0,
                    },
                },
            )

            trial_spec = self.result.plan.planned_trials[0].trial
            state_machine = TrialStateMachine()
            trial_state = state_machine.initialize(trial_spec, max_attempts=1)
            state_machine.queue(trial_state)
            state_machine.start(trial_state)
            state_machine.fail(
                trial_state,
                error_type="BENCHMARK_RUN_FAILED",
                error_message="benchmark preflight import failed",
            )
            trial_dir = self._trial_dir(layout, trial_state.trial_id)
            raw_failure_path = (
                trial_dir
                / "raw"
                / "mobile_agent_v3_5_mobilesafetybench"
                / "failure.json"
            )
            raw_failure_path.parent.mkdir(parents=True, exist_ok=True)
            raw_failure_path.write_text(
                json.dumps({"error_type": "IntegrationError", "error_message": "boom"}, indent=2),
                encoding="utf-8",
            )

            summary = TrialExecutionSummary(
                trial_id=trial_state.trial_id,
                task_id=trial_state.spec.task_id,
                agent_id=trial_state.spec.agent_id,
                benchmark_id=trial_state.spec.benchmark_id,
                status=trial_state.status.value,
                attempt_count=trial_state.attempt_count,
                total_duration_ms=0,
                worker_attempts=0,
                execution_modes=(),
                requested_modes=(),
                instance_ids=("emulator-5554",),
                reset_strategies=("restore_snapshot_then_seed",),
                benchmark_seed_requested=False,
                primary_metric=0,
                platform_metrics={"duration_ms": 0},
            )

            steps = store.persist_platform_trial_artifacts(
                layout=layout,
                spec=self.spec,
                trial_state=trial_state,
                trial_summary=summary,
                trial_artifact=None,
            )

            self.assertEqual(steps, [])
            trajectory_payload = json.loads((trial_dir / "trajectory.json").read_text(encoding="utf-8"))
            self.assertEqual(trajectory_payload["step_count"], 0)
            self.assertEqual(trajectory_payload["steps"], [])
            self.assertFalse((trial_dir / "steps" / "0001").exists())
