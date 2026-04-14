from __future__ import annotations

import sys
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from snowl_mobile.adapters.builtin import create_builtin_registry
from snowl_mobile.artifacts.store import ArtifactStore
from snowl_mobile.core.planner import ExecutionPlanner
from snowl_mobile.core.runtime_recipe import RuntimeRecipe
from snowl_mobile.core.config_loader import load_project_spec
from snowl_mobile.core.trial_state_machine import TrialStateMachine
from snowl_mobile.runtime.trial_orchestrator import TrialOrchestrator
from snowl_mobile.runtime.worker_launcher import WorkerLaunchOutcome, WorkerLauncher
from snowl_mobile.runtime.worker_protocol import WorkerResult
from snowl_mobile.schedulers.retry_controller import RetryController
from snowl_mobile.schedulers.scheduler import Scheduler


class WorkerRuntimeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = load_project_spec(ROOT / "project.example.yml")
        self.planner = ExecutionPlanner(registry=create_builtin_registry())
        self.plan = self.planner.plan(self.spec)
        self.state_machine = TrialStateMachine()

    def _trial_for_agent(self, agent_id: str):
        return next(
            entry.trial for entry in self.plan.planned_trials if entry.trial.agent_id == agent_id
        )

    def _started_state(self, agent_id: str, *, runtime_recipe: RuntimeRecipe | None = None):
        trial = self._trial_for_agent(agent_id)
        if runtime_recipe is not None:
            trial = replace(trial, runtime_recipe=runtime_recipe)
        state = self.state_machine.initialize(trial, max_attempts=3)
        self.state_machine.queue(state, reason="test-submit")
        self.state_machine.start(state, reason="test-dispatch")
        return state

    def test_worker_spec_maps_runtime_recipe_to_execution_mode(self) -> None:
        launcher = WorkerLauncher(cwd=ROOT)
        text_state = self._started_state("dummy_text_agent")
        vision_state = self._started_state("dummy_vision_agent")

        text_worker = launcher.build_worker_spec(text_state)
        vision_worker = launcher.build_worker_spec(vision_state)

        self.assertEqual(text_worker.execution_mode, "in_process")
        self.assertEqual(text_worker.requested_mode, "in_process")
        self.assertEqual(vision_worker.execution_mode, "subprocess")
        self.assertEqual(vision_worker.requested_mode, "container")
        self.assertEqual(vision_worker.extra["bridge_id"], "dummy_vision__dummy_benchmark")
        self.assertEqual(vision_worker.extra["pair_recipe_id"], "dummy_vision_bridge_recipe")

    def test_in_process_worker_executes_dummy_trial(self) -> None:
        launcher = WorkerLauncher(cwd=ROOT)
        state = self._started_state("dummy_text_agent")

        outcome = launcher.execute_trial(state)

        self.assertTrue(outcome.result.success)
        self.assertEqual(outcome.result.execution_mode, "in_process")
        self.assertEqual(outcome.result.payload["agent_display_name"], "Dummy Text Agent")

    def test_orchestrator_retries_retryable_worker_failure(self) -> None:
        orchestrator = TrialOrchestrator(
            worker_launcher=WorkerLauncher(cwd=ROOT),
            scheduler=Scheduler(state_machine=self.planner.state_machine),
            state_machine=self.planner.state_machine,
        )

        result = orchestrator.run_plan(
            self.plan,
            retry_controller=RetryController(self.spec.retries),
        )

        self.assertEqual(result.scheduler_snapshot.succeeded, 4)
        self.assertEqual(result.scheduler_snapshot.failed, 0)
        self.assertEqual(len(result.worker_attempts), 6)
        self.assertTrue(
            any(
                attempt.result.execution_mode == "subprocess"
                and not attempt.result.success
                and attempt.result.error_type == "WORKER_TRANSIENT_ERROR"
                for attempt in result.worker_attempts
            )
        )

    def test_subprocess_worker_crash_is_reported(self) -> None:
        launcher = WorkerLauncher(cwd=ROOT)
        vision_trial = self._trial_for_agent("dummy_vision_agent")
        state = self._started_state(
            "dummy_vision_agent",
            runtime_recipe=replace(
                vision_trial.runtime_recipe,
                env_vars={"SNOWL_DUMMY_WORKER_BEHAVIOR": "crash"},
            ),
        )

        outcome = launcher.execute_trial(state, trial_timeout_sec=2)

        self.assertFalse(outcome.result.success)
        self.assertEqual(outcome.result.error_type, "WORKER_CRASH")
        self.assertTrue(outcome.result.retryable)

    def test_subprocess_worker_timeout_is_reported(self) -> None:
        launcher = WorkerLauncher(cwd=ROOT)
        vision_trial = self._trial_for_agent("dummy_vision_agent")
        state = self._started_state(
            "dummy_vision_agent",
            runtime_recipe=replace(
                vision_trial.runtime_recipe,
                env_vars={"SNOWL_DUMMY_WORKER_BEHAVIOR": "timeout"},
            ),
        )

        outcome = launcher.execute_trial(state, trial_timeout_sec=1)

        self.assertFalse(outcome.result.success)
        self.assertEqual(outcome.result.error_type, "WORKER_TIMEOUT")
        self.assertTrue(outcome.result.retryable)

    def test_subprocess_worker_malformed_response_is_reported(self) -> None:
        launcher = WorkerLauncher(cwd=ROOT)
        vision_trial = self._trial_for_agent("dummy_vision_agent")
        state = self._started_state(
            "dummy_vision_agent",
            runtime_recipe=replace(
                vision_trial.runtime_recipe,
                env_vars={"SNOWL_DUMMY_WORKER_BEHAVIOR": "malformed"},
            ),
        )

        outcome = launcher.execute_trial(state, trial_timeout_sec=2)

        self.assertFalse(outcome.result.success)
        self.assertEqual(outcome.result.error_type, "WORKER_PROTOCOL_ERROR")
        self.assertTrue(outcome.result.retryable)

    def test_platform_pipeline_dispatches_trials_concurrently_when_batch_size_exceeds_one(self) -> None:
        class SlowSuccessWorkerLauncher(WorkerLauncher):
            def __init__(self) -> None:
                super().__init__(cwd=ROOT)
                self._lock = threading.Lock()
                self.active = 0
                self.max_active = 0

            def execute_trial(self, trial_state, **kwargs):  # type: ignore[override]
                worker_spec = self.build_worker_spec(trial_state)
                with self._lock:
                    self.active += 1
                    self.max_active = max(self.max_active, self.active)
                try:
                    time.sleep(0.2)
                finally:
                    with self._lock:
                        self.active -= 1
                return WorkerLaunchOutcome(
                    worker_spec=worker_spec,
                    result=WorkerResult.success_result(
                        worker_id=worker_spec.worker_id,
                        trial_id=trial_state.trial_id,
                        execution_mode=worker_spec.execution_mode,
                        requested_mode=worker_spec.requested_mode,
                        attempt=trial_state.attempt_count,
                        worker_pid=None,
                        started_at="2026-04-09T00:00:00+00:00",
                        finished_at="2026-04-09T00:00:01+00:00",
                        duration_ms=200,
                        payload={},
                    ),
                )

        launcher = SlowSuccessWorkerLauncher()
        orchestrator = TrialOrchestrator(worker_launcher=launcher)

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore()
            layout = store.initialize_run_directory(
                spec=self.spec,
                project_source=ROOT / "project.example.yml",
                run_dir=Path(temp_dir) / "parallel-platform-run",
                run_id="parallel-platform-run",
                plan_payload=self.plan.to_summary(),
                summary_payload={"run_id": "parallel-platform-run", "status": "RUNNING"},
            )
            result = orchestrator.run_platform_pipeline(
                self.plan,
                spec=self.spec,
                registry=create_builtin_registry(),
                retry_controller=RetryController(self.spec.retries),
                run_layout=layout,
                device_count=2,
            )

        self.assertEqual(result.scheduler_snapshot.succeeded, 4)
        self.assertEqual(result.scheduler_snapshot.failed, 0)
        self.assertGreaterEqual(launcher.max_active, 2)
