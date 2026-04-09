from __future__ import annotations

from dataclasses import dataclass

from snowl_mobile.core.planner import ExecutionPlan
from snowl_mobile.core.project_spec import ProjectSpec
from snowl_mobile.core.trial_state_machine import TrialStateMachine
from snowl_mobile.devices.emulator_pool import EmulatorPoolManager
from snowl_mobile.devices.reset_strategy import ResetManager
from snowl_mobile.schedulers.scheduler import Scheduler


@dataclass(frozen=True, slots=True)
class EmulatorAssignmentRecord:
    trial_id: str
    instance_id: str
    adb_serial: str
    health_status: str
    reset_strategy: str
    benchmark_seed_requested: bool
    released: bool


@dataclass(frozen=True, slots=True)
class EmulatorDemoResult:
    assignments: tuple[EmulatorAssignmentRecord, ...]
    provider_events: tuple[dict[str, object], ...]
    pool_snapshot: dict[str, object]
    scheduler_snapshot: dict[str, object]
    queue_blocked_while_busy: bool
    instances: tuple[dict[str, object], ...]

    def to_summary(self) -> dict[str, object]:
        return {
            "queue_blocked_while_busy": self.queue_blocked_while_busy,
            "pool": self.pool_snapshot,
            "scheduler": self.scheduler_snapshot,
            "assignments": [
                {
                    "trial_id": record.trial_id,
                    "instance_id": record.instance_id,
                    "adb_serial": record.adb_serial,
                    "health_status": record.health_status,
                    "reset_strategy": record.reset_strategy,
                    "benchmark_seed_requested": record.benchmark_seed_requested,
                    "released": record.released,
                }
                for record in self.assignments
            ],
            "provider_events": list(self.provider_events),
            "instances": list(self.instances),
        }


def run_fake_emulator_demo(
    *,
    spec: ProjectSpec,
    plan: ExecutionPlan,
    instance_count: int = 2,
) -> EmulatorDemoResult:
    state_machine = TrialStateMachine()
    scheduler = Scheduler(state_machine=state_machine)
    reset_manager = ResetManager(policy=spec.reset)
    profile = next(
        profile
        for profile in spec.devices.emulator_profiles
        if profile.profile_id == spec.devices.default_profile
    )
    pool = EmulatorPoolManager()
    pool.provision_pool(profile=profile, instance_count=instance_count)

    trial_states = [
        state_machine.initialize(entry.trial, max_attempts=spec.retries.max_trial_retries + 1)
        for entry in plan.planned_trials
    ]
    scheduler.submit_trials(trial_states)

    maintenance_lease = pool.acquire_lease(
        trial_id="maintenance-hold",
        profile_id=spec.devices.default_profile,
    )

    assignments: list[EmulatorAssignmentRecord] = []
    queue_blocked_while_busy = False

    while True:
        dispatch = scheduler.poll_next_runnable_trial_with_emulator(pool)
        if dispatch is None:
            if scheduler.has_waiting_trials():
                queue_blocked_while_busy = True
                if maintenance_lease is not None:
                    pool.release_instance(maintenance_lease)
                    maintenance_lease = None
                    continue
            break

        health_status = pool.health_check(dispatch.emulator_lease.instance_id)
        benchmark_requires_seed = bool(
            next(
                benchmark
                for benchmark in spec.benchmarks
                if benchmark.benchmark_id == dispatch.trial_state.spec.benchmark_id
            ).reset_requirements.get("requires_task_seed", False)
        )
        reset_record = reset_manager.reset_for_trial(
            pool_manager=pool,
            lease=dispatch.emulator_lease,
            benchmark_reset_policy=dispatch.trial_state.spec.runtime_recipe.reset_policy,
            benchmark_requires_seed=benchmark_requires_seed,
        )
        if (
            not pool.available_instances(profile_id=spec.devices.default_profile)
            and scheduler.has_waiting_trials()
        ):
            queue_blocked_while_busy = True

        scheduler.mark_trial_finished(dispatch.trial_state.trial_id, success=True)
        lease = scheduler.release_trial_lease(dispatch.trial_state.trial_id)
        if lease is not None:
            pool.release_instance(lease)

        assignments.append(
            EmulatorAssignmentRecord(
                trial_id=dispatch.trial_state.trial_id,
                instance_id=dispatch.emulator_lease.instance_id,
                adb_serial=dispatch.emulator_lease.adb_serial,
                health_status=health_status.value,
                reset_strategy=reset_record.strategy,
                benchmark_seed_requested=reset_record.benchmark_seed_requested,
                released=True,
            )
        )

    if maintenance_lease is not None:
        pool.release_instance(maintenance_lease)

    return EmulatorDemoResult(
        assignments=tuple(assignments),
        provider_events=tuple(event.to_dict() for event in pool.provider_events()),
        pool_snapshot=pool.snapshot().to_dict(),
        scheduler_snapshot=scheduler.snapshot().to_dict(),
        queue_blocked_while_busy=queue_blocked_while_busy,
        instances=tuple(
            {
                "instance_id": instance.instance_id,
                "adb_serial": instance.adb_serial,
                "appium_port": instance.appium_port,
                "grpc_port": instance.grpc_port,
                "avd_name": instance.avd_name,
                "snapshot_name": instance.snapshot_name,
                "status": instance.status.value,
                "current_trial_id": instance.current_trial_id,
                "last_heartbeat_at": instance.last_heartbeat_at,
                "health_status": instance.health_status.value,
            }
            for instance in pool.instances()
        ),
    )
