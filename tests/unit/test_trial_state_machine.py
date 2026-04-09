from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from snowl_mobile.adapters.builtin import create_builtin_registry
from snowl_mobile.core.errors import StateTransitionError
from snowl_mobile.core.planner import ExecutionPlanner
from snowl_mobile.core.config_loader import load_project_spec
from snowl_mobile.core.trial_state_machine import TrialStateMachine


class TrialStateMachineTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = load_project_spec(ROOT / "project.example.yml")
        plan = ExecutionPlanner(registry=create_builtin_registry()).plan(self.spec)
        self.trial = plan.planned_trials[0].trial
        self.state_machine = TrialStateMachine()

    def test_valid_lifecycle_reaches_completed(self) -> None:
        state = self.state_machine.initialize(self.trial, max_attempts=3)
        self.state_machine.queue(state, reason="submit")
        self.state_machine.start(state, reason="dispatch")
        self.state_machine.complete(state, reason="success")

        self.assertEqual(state.status.value, "COMPLETED")
        self.assertEqual(
            [transition.to_status for transition in state.history],
            ["SCHEDULED", "PREPARING", "RUNNING", "SCORING", "COMPLETED"],
        )

    def test_invalid_transition_raises(self) -> None:
        state = self.state_machine.initialize(self.trial, max_attempts=3)
        with self.assertRaises(StateTransitionError):
            self.state_machine.complete(state, reason="invalid")

    def test_retry_transition_is_recorded(self) -> None:
        state = self.state_machine.initialize(self.trial, max_attempts=3)
        self.state_machine.queue(state, reason="submit")
        self.state_machine.start(state, reason="dispatch")
        self.state_machine.fail(
            state,
            error_type="MODEL_API_ERROR",
            error_message="transient",
        )
        self.state_machine.mark_retry_waiting(state, reason="retry allowed")
        self.state_machine.queue(state, reason="requeue")

        self.assertEqual(state.status.value, "SCHEDULED")
        self.assertEqual(
            [transition.to_status for transition in state.history][-3:],
            ["FAILED", "RETRY_WAITING", "SCHEDULED"],
        )
