from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from snowl_mobile.adapters.builtin import create_builtin_registry
from snowl_mobile.core.config_loader import load_project_spec
from snowl_mobile.core.planner import ExecutionPlanner
from snowl_mobile.runtime.trial_orchestrator import TrialOrchestrator
from snowl_mobile.schedulers.retry_controller import RetryController, TrialFailure
from snowl_mobile.schedulers.scheduler import Scheduler


class SchedulerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        spec = load_project_spec(ROOT / "project.example.yml")
        planner = ExecutionPlanner(registry=create_builtin_registry())
        plan = planner.plan(spec)
        self.retry_controller = RetryController(spec.retries)
        self.state = planner.state_machine.initialize(
            plan.planned_trials[1].trial,
            max_attempts=self.retry_controller.max_attempts,
        )
        self.scheduler = Scheduler(state_machine=planner.state_machine)
        self.scheduler.submit_trial(self.state)

    def test_retryable_failure_requeues_trial(self) -> None:
        trial = self.scheduler.poll_next_runnable_trial()
        self.assertIsNotNone(trial)
        decision = self.scheduler.mark_trial_finished(
            trial.trial_id,
            success=False,
            retry_controller=self.retry_controller,
            failure=TrialFailure(
                error_type="MODEL_API_ERROR",
                message="transient",
            ),
        )
        snapshot = self.scheduler.snapshot()

        self.assertIsNotNone(decision)
        self.assertTrue(decision.should_retry)
        self.assertEqual(snapshot.queued, 1)
        self.assertEqual(self.state.status.value, "SCHEDULED")

    def test_non_retryable_failure_stays_failed(self) -> None:
        trial = self.scheduler.poll_next_runnable_trial()
        self.assertIsNotNone(trial)
        decision = self.scheduler.mark_trial_finished(
            trial.trial_id,
            success=False,
            retry_controller=self.retry_controller,
            failure=TrialFailure(
                error_type="BENCHMARK_RUNTIME_ERROR",
                message="permanent",
            ),
        )
        snapshot = self.scheduler.snapshot()

        self.assertIsNotNone(decision)
        self.assertFalse(decision.should_retry)
        self.assertEqual(snapshot.failed, 1)
        self.assertEqual(self.state.status.value, "FAILED")

    def test_interrupted_trial_can_be_marked_aborted_without_failed_count(self) -> None:
        trial = self.scheduler.poll_next_runnable_trial()
        self.assertIsNotNone(trial)

        self.scheduler.mark_trial_aborted(
            trial.trial_id,
            reason="KeyboardInterrupt",
            failure=TrialFailure(error_type="RUN_INTERRUPTED", message="KeyboardInterrupt"),
        )
        snapshot = self.scheduler.snapshot()

        self.assertEqual(snapshot.failed, 0)
        self.assertEqual(snapshot.exact_status_counts["ABORTED"], 1)
        self.assertEqual(self.state.status.value, "ABORTED")
        self.assertEqual(self.state.last_error_type, "RUN_INTERRUPTED")

    def test_orchestrator_classifies_keyboard_interrupt_as_run_interruption(self) -> None:
        orchestrator = TrialOrchestrator()

        error_type, message = orchestrator._classify_runtime_failure(  # noqa: SLF001
            RuntimeError("bridge subprocess exited after KeyboardInterrupt")
        )

        self.assertEqual(error_type, "RUN_INTERRUPTED")
        self.assertIn("KeyboardInterrupt", message)
