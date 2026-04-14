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
from snowl_mobile.core.trial_state_machine import TrialStateMachine
from snowl_mobile.devices.emulator_instance import HealthStatus
from snowl_mobile.devices.emulator_pool import EmulatorPoolManager
from snowl_mobile.devices.reset_strategy import ResetManager
from snowl_mobile.schedulers.scheduler import Scheduler


class EmulatorPoolTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = load_project_spec(ROOT / "project.example.yml")
        self.plan = ExecutionPlanner(registry=create_builtin_registry()).plan(self.spec)
        self.profile = next(
            profile
            for profile in self.spec.devices.emulator_profiles
            if profile.profile_id == self.spec.devices.default_profile
        )

    def test_pool_provision_and_health_filtering(self) -> None:
        pool = EmulatorPoolManager()
        instances = pool.provision_pool(profile=self.profile, instance_count=2)

        self.assertEqual(len(instances), 2)
        self.assertEqual(pool.snapshot().idle_instances, 2)

        pool.set_health(instances[0].instance_id, HealthStatus.UNHEALTHY)
        available = pool.available_instances(profile_id=self.profile.profile_id)

        self.assertEqual(len(available), 1)
        self.assertEqual(available[0].instance_id, instances[1].instance_id)

    def test_reset_manager_records_restore_snapshot_then_seed(self) -> None:
        pool = EmulatorPoolManager()
        pool.provision_pool(profile=self.profile, instance_count=1)
        lease = pool.acquire_lease(trial_id="trial-001", profile_id=self.profile.profile_id)
        self.assertIsNotNone(lease)

        record = ResetManager(policy=self.spec.reset).reset_for_trial(
            pool_manager=pool,
            lease=lease,
            benchmark_reset_policy="snapshot_then_seed",
            benchmark_requires_seed=True,
        )

        self.assertEqual(record.strategy, "restore_snapshot_then_seed")
        self.assertTrue(record.snapshot_restored)
        self.assertTrue(record.benchmark_seed_requested)

    def test_scheduler_waits_when_all_emulator_slots_are_busy(self) -> None:
        pool = EmulatorPoolManager()
        pool.provision_pool(profile=self.profile, instance_count=1)

        state_machine = TrialStateMachine()
        scheduler = Scheduler(state_machine=state_machine)
        trial_states = [
            state_machine.initialize(entry.trial, max_attempts=3)
            for entry in self.plan.planned_trials
        ]
        scheduler.submit_trials(trial_states)

        first_dispatch = scheduler.poll_next_runnable_trial_with_emulator(pool)
        self.assertIsNotNone(first_dispatch)
        self.assertEqual(first_dispatch.trial_state.trial_id, self.plan.planned_trials[0].trial.trial_id)

        second_dispatch = scheduler.poll_next_runnable_trial_with_emulator(pool)
        self.assertIsNone(second_dispatch)
        self.assertTrue(scheduler.has_waiting_trials())

        scheduler.mark_trial_finished(first_dispatch.trial_state.trial_id, success=True)
        first_lease = scheduler.release_trial_lease(first_dispatch.trial_state.trial_id)
        self.assertIsNotNone(first_lease)
        pool.release_instance(first_lease)

        retry_dispatch = scheduler.poll_next_runnable_trial_with_emulator(pool)
        self.assertIsNotNone(retry_dispatch)
        self.assertEqual(retry_dispatch.trial_state.trial_id, self.plan.planned_trials[1].trial.trial_id)
