from __future__ import annotations

import logging
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from snowl_mobile.artifacts.paths import RunLayout
from snowl_mobile.artifacts.trajectory import TrajectoryStep
from snowl_mobile.core.enums import DeviceMode
from snowl_mobile.core.policies import RetryPolicy
from snowl_mobile.core.planner import ExecutionPlan
from snowl_mobile.core.project_spec import ProjectSpec
from snowl_mobile.core.registry import Registry
from snowl_mobile.core.states import RunStatus, TrialStatus
from snowl_mobile.core.trial_context import TrialContext
from snowl_mobile.core.trial_state_machine import TrialState, TrialStateMachine
from snowl_mobile.devices.emulator_pool import create_emulator_pool_manager
from snowl_mobile.devices.reset_strategy import ResetManager, ResetRecord
from snowl_mobile.scoring.score_bundle import ScoreBundle
from snowl_mobile.runtime.worker_launcher import WorkerLaunchOutcome, WorkerLauncher
from snowl_mobile.schedulers.retry_controller import RetryController, TrialFailure
from snowl_mobile.schedulers.scheduler import Scheduler, SchedulerSnapshot


LOGGER = logging.getLogger(__name__)
MIN_NON_FATAL_TRIAL_RETRIES = 3
NON_FATAL_TASK_RETRYABLE_ERRORS = (
    "ADB_BACKEND_ERROR",
    "AGENT_WORKER_CRASH",
    "BENCHMARK_RUN_FAILED",
    "PAIR_RUNTIME_ERROR",
    "WORKER_CRASH",
    "WORKER_PROTOCOL_ERROR",
    "WORKER_TIMEOUT",
    "WORKER_TRANSIENT_ERROR",
)


def _utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class OrchestratedRunResult:
    plan: ExecutionPlan
    scheduler_snapshot: SchedulerSnapshot
    trial_states: tuple[TrialState, ...]
    worker_attempts: tuple[WorkerLaunchOutcome, ...]

    def to_summary(self) -> dict[str, object]:
        return {
            "run": {
                "run_id": self.plan.run_id,
                "status": self.plan.run_context.status.value,
                "planned_trials": self.plan.run_context.planned_trials,
                "diagnostics": self.plan.run_context.diagnostics,
            },
            "scheduler": self.scheduler_snapshot.to_dict(),
            "worker_attempts": [
                {
                    "trial_id": attempt.result.trial_id,
                    "worker_id": attempt.result.worker_id,
                    "execution_mode": attempt.result.execution_mode,
                    "requested_mode": attempt.result.requested_mode,
                    "attempt": attempt.result.attempt,
                    "success": attempt.result.success,
                    "retryable": attempt.result.retryable,
                    "error_type": attempt.result.error_type,
                    "error_message": attempt.result.error_message,
                }
                for attempt in self.worker_attempts
            ],
            "trials": [trial_state.to_summary() for trial_state in self.trial_states],
        }


@dataclass(frozen=True, slots=True)
class TrialExecutionSummary:
    trial_id: str
    task_id: str
    agent_id: str
    benchmark_id: str
    status: str
    attempt_count: int
    total_duration_ms: int
    worker_attempts: int
    execution_modes: tuple[str, ...]
    requested_modes: tuple[str, ...]
    instance_ids: tuple[str, ...]
    reset_strategies: tuple[str, ...]
    benchmark_seed_requested: bool
    primary_metric: int
    platform_metrics: dict[str, object]
    last_error_type: str | None = None
    last_error_message: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "trial_id": self.trial_id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "benchmark_id": self.benchmark_id,
            "status": self.status,
            "attempt_count": self.attempt_count,
            "total_duration_ms": self.total_duration_ms,
            "worker_attempts": self.worker_attempts,
            "execution_modes": list(self.execution_modes),
            "requested_modes": list(self.requested_modes),
            "instance_ids": list(self.instance_ids),
            "reset_strategies": list(self.reset_strategies),
            "benchmark_seed_requested": self.benchmark_seed_requested,
            "primary_metric": self.primary_metric,
            "platform_metrics": self.platform_metrics,
            "last_error_type": self.last_error_type,
            "last_error_message": self.last_error_message,
        }


@dataclass(frozen=True, slots=True)
class TrialArtifactRecord:
    trial_id: str
    score_bundle: ScoreBundle
    trajectory_steps: tuple[TrajectoryStep, ...]
    raw_artifacts: dict[str, str]
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DummyPipelineRunResult:
    plan: ExecutionPlan
    scheduler_snapshot: SchedulerSnapshot
    trial_states: tuple[TrialState, ...]
    worker_attempts: tuple[WorkerLaunchOutcome, ...]
    trial_summaries: tuple[TrialExecutionSummary, ...]
    reset_records: tuple[ResetRecord, ...]
    pool_snapshot: dict[str, object]
    provider_events: tuple[dict[str, object], ...]
    started_at: str
    finished_at: str
    total_duration_ms: int

    def to_summary(self) -> dict[str, object]:
        completed = self.scheduler_snapshot.succeeded
        failed = self.scheduler_snapshot.failed
        total_trials = len(self.trial_summaries)
        success_rate = 0.0 if total_trials == 0 else round(completed / total_trials, 4)
        avg_trial_duration_ms = (
            0
            if total_trials == 0
            else round(sum(summary.total_duration_ms for summary in self.trial_summaries) / total_trials, 2)
        )
        max_trial_duration_ms = max((summary.total_duration_ms for summary in self.trial_summaries), default=0)
        return {
            "run": {
                "run_id": self.plan.run_id,
                "status": self.plan.run_context.status.value,
                "planned_trials": self.plan.run_context.planned_trials,
                "diagnostics": self.plan.run_context.diagnostics,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "total_duration_ms": self.total_duration_ms,
            },
            "counts": {
                "planned_trials": self.plan.run_context.planned_trials,
                "diagnostics": self.plan.run_context.diagnostics,
                "completed": completed,
                "failed": failed,
                "retrying": self.scheduler_snapshot.retrying,
                "queued": self.scheduler_snapshot.queued,
                "running": self.scheduler_snapshot.running,
                "skipped": self.scheduler_snapshot.skipped,
            },
            "metrics_summary": {
                "success_rate": success_rate,
                "total_worker_attempts": len(self.worker_attempts),
                "avg_trial_duration_ms": avg_trial_duration_ms,
                "max_trial_duration_ms": max_trial_duration_ms,
            },
            "scheduler": self.scheduler_snapshot.to_dict(),
            "pool": self.pool_snapshot,
            "trials": [summary.to_dict() for summary in self.trial_summaries],
            "worker_attempts": [
                {
                    "trial_id": attempt.result.trial_id,
                    "worker_id": attempt.result.worker_id,
                    "attempt": attempt.result.attempt,
                    "success": attempt.result.success,
                    "retryable": attempt.result.retryable,
                    "execution_mode": attempt.result.execution_mode,
                    "requested_mode": attempt.result.requested_mode,
                    "duration_ms": attempt.result.duration_ms,
                    "error_type": attempt.result.error_type,
                    "error_message": attempt.result.error_message,
                }
                for attempt in self.worker_attempts
            ],
            "provider_events": list(self.provider_events),
        }


@dataclass(frozen=True, slots=True)
class PlatformPipelineRunResult:
    plan: ExecutionPlan
    scheduler_snapshot: SchedulerSnapshot
    trial_states: tuple[TrialState, ...]
    worker_attempts: tuple[WorkerLaunchOutcome, ...]
    trial_summaries: tuple[TrialExecutionSummary, ...]
    trial_artifacts: tuple[TrialArtifactRecord, ...]
    reset_records: tuple[ResetRecord, ...]
    pool_snapshot: dict[str, object]
    provider_events: tuple[dict[str, object], ...]
    started_at: str
    finished_at: str
    total_duration_ms: int
    notes: tuple[str, ...] = ()

    def to_summary(self) -> dict[str, object]:
        completed = self.scheduler_snapshot.succeeded
        failed = self.scheduler_snapshot.failed
        total_trials = len(self.trial_summaries)
        success_rate = 0.0 if total_trials == 0 else round(completed / total_trials, 4)
        avg_trial_duration_ms = (
            0
            if total_trials == 0
            else round(sum(summary.total_duration_ms for summary in self.trial_summaries) / total_trials, 2)
        )
        max_trial_duration_ms = max((summary.total_duration_ms for summary in self.trial_summaries), default=0)
        return {
            "run": {
                "run_id": self.plan.run_id,
                "status": self.plan.run_context.status.value,
                "planned_trials": self.plan.run_context.planned_trials,
                "diagnostics": self.plan.run_context.diagnostics,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "total_duration_ms": self.total_duration_ms,
            },
            "counts": {
                "planned_trials": self.plan.run_context.planned_trials,
                "diagnostics": self.plan.run_context.diagnostics,
                "completed": completed,
                "failed": failed,
                "retrying": self.scheduler_snapshot.retrying,
                "queued": self.scheduler_snapshot.queued,
                "running": self.scheduler_snapshot.running,
                "skipped": self.scheduler_snapshot.skipped,
            },
            "metrics_summary": {
                "success_rate": success_rate,
                "total_worker_attempts": len(self.worker_attempts),
                "avg_trial_duration_ms": avg_trial_duration_ms,
                "max_trial_duration_ms": max_trial_duration_ms,
            },
            "scheduler": self.scheduler_snapshot.to_dict(),
            "pool": self.pool_snapshot,
            "trials": [summary.to_dict() for summary in self.trial_summaries],
            "worker_attempts": [
                {
                    "trial_id": attempt.result.trial_id,
                    "worker_id": attempt.result.worker_id,
                    "attempt": attempt.result.attempt,
                    "success": attempt.result.success,
                    "retryable": attempt.result.retryable,
                    "execution_mode": attempt.result.execution_mode,
                    "requested_mode": attempt.result.requested_mode,
                    "duration_ms": attempt.result.duration_ms,
                    "error_type": attempt.result.error_type,
                    "error_message": attempt.result.error_message,
                }
                for attempt in self.worker_attempts
            ],
            "provider_events": list(self.provider_events),
            "notes": list(self.notes),
        }


@dataclass(frozen=True, slots=True)
class _PlatformDispatchExecutionResult:
    success: bool
    trial_artifact: TrialArtifactRecord | None = None
    runtime_meta: dict[str, object] | None = None
    worker_attempt: WorkerLaunchOutcome | None = None
    notes: tuple[str, ...] = ()
    failure: TrialFailure | None = None
    abort_immediately: bool = False


class TrialOrchestrator:
    def __init__(
        self,
        *,
        worker_launcher: WorkerLauncher | None = None,
        scheduler: Scheduler | None = None,
        retry_controller: RetryController | None = None,
        state_machine: TrialStateMachine | None = None,
    ) -> None:
        self.state_machine = state_machine or TrialStateMachine()
        self.worker_launcher = worker_launcher or WorkerLauncher()
        self.scheduler = scheduler or Scheduler(state_machine=self.state_machine)
        self.retry_controller = retry_controller

    def run_plan(self, plan: ExecutionPlan, *, retry_controller: RetryController) -> OrchestratedRunResult:
        self.retry_controller = retry_controller
        trial_states = [
            self.state_machine.initialize(
                entry.trial,
                max_attempts=retry_controller.max_attempts,
            )
            for entry in plan.planned_trials
        ]
        self.scheduler.submit_trials(trial_states)
        plan.run_context.sync_scheduler_counts(self.scheduler.snapshot().to_dict())

        worker_attempts: list[WorkerLaunchOutcome] = []
        while True:
            trial_state = self.scheduler.poll_next_runnable_trial()
            if trial_state is None:
                break

            outcome = self.worker_launcher.execute_trial(trial_state)
            worker_attempts.append(outcome)
            if outcome.result.success:
                self.scheduler.mark_trial_finished(trial_state.trial_id, success=True)
            else:
                self.scheduler.mark_trial_finished(
                    trial_state.trial_id,
                    success=False,
                    retry_controller=retry_controller,
                    failure=outcome.result.to_trial_failure(),
                )
            plan.run_context.sync_scheduler_counts(self.scheduler.snapshot().to_dict())

        final_snapshot = self.scheduler.snapshot()
        plan.run_context.sync_scheduler_counts(final_snapshot.to_dict())
        return OrchestratedRunResult(
            plan=plan,
            scheduler_snapshot=final_snapshot,
            trial_states=tuple(self.scheduler.trial_states()),
            worker_attempts=tuple(worker_attempts),
        )

    def run_dummy_pipeline(
        self,
        plan: ExecutionPlan,
        *,
        spec: ProjectSpec,
        retry_controller: RetryController,
        device_count: int | None = None,
    ) -> DummyPipelineRunResult:
        benchmark_index = {
            benchmark.benchmark_id: benchmark
            for benchmark in spec.benchmarks
        }
        profile = next(
            profile
            for profile in spec.devices.emulator_profiles
            if profile.profile_id == spec.devices.default_profile
        )
        instance_count = device_count or max(1, spec.runtime.batch_size)
        pool_manager = create_emulator_pool_manager(
            device_mode=spec.devices.device_mode,
            adb_serials=spec.devices.adb_serials,
            avd_names=spec.devices.avd_names,
        )
        pool_manager.provision_pool(profile=profile, instance_count=instance_count)
        reset_manager = ResetManager(policy=spec.reset)

        trial_states = [
            self.state_machine.initialize(
                entry.trial,
                max_attempts=retry_controller.max_attempts,
            )
            for entry in plan.planned_trials
        ]
        self.scheduler.submit_trials(trial_states)
        plan.run_context.sync_scheduler_counts(self.scheduler.snapshot().to_dict())

        started_at = _utcnow()
        started_monotonic = time.monotonic()
        worker_attempts: list[WorkerLaunchOutcome] = []
        assignment_history: dict[str, list[str]] = {}
        reset_history: dict[str, list[ResetRecord]] = {}

        while True:
            dispatch = self.scheduler.poll_next_runnable_trial_with_emulator(pool_manager)
            if dispatch is None:
                break

            benchmark = benchmark_index[dispatch.trial_state.spec.benchmark_id]
            reset_record = reset_manager.reset_for_trial(
                pool_manager=pool_manager,
                lease=dispatch.emulator_lease,
                benchmark_reset_policy=dispatch.trial_state.spec.runtime_recipe.reset_policy,
                benchmark_requires_seed=bool(
                    benchmark.reset_requirements.get("requires_task_seed", False)
                ),
            )
            assignment_history.setdefault(dispatch.trial_state.trial_id, []).append(
                dispatch.emulator_lease.instance_id
            )
            reset_history.setdefault(dispatch.trial_state.trial_id, []).append(reset_record)

            outcome = self.worker_launcher.execute_trial(dispatch.trial_state)
            worker_attempts.append(outcome)

            if outcome.result.success:
                self.scheduler.mark_trial_finished(dispatch.trial_state.trial_id, success=True)
            else:
                self.scheduler.mark_trial_finished(
                    dispatch.trial_state.trial_id,
                    success=False,
                    retry_controller=retry_controller,
                    failure=outcome.result.to_trial_failure(),
                )

            lease = self.scheduler.release_trial_lease(dispatch.trial_state.trial_id)
            if lease is not None:
                pool_manager.release_instance(lease)
            plan.run_context.sync_scheduler_counts(self.scheduler.snapshot().to_dict())

        finished_at = _utcnow()
        final_snapshot = self.scheduler.snapshot()
        plan.run_context.sync_scheduler_counts(final_snapshot.to_dict())
        trial_summaries = self._build_trial_summaries(
            trial_states=self.scheduler.trial_states(),
            worker_attempts=worker_attempts,
            assignment_history=assignment_history,
            reset_history=reset_history,
        )
        return DummyPipelineRunResult(
            plan=plan,
            scheduler_snapshot=final_snapshot,
            trial_states=tuple(self.scheduler.trial_states()),
            worker_attempts=tuple(worker_attempts),
            trial_summaries=trial_summaries,
            reset_records=reset_manager.records(),
            pool_snapshot=pool_manager.snapshot().to_dict(),
            provider_events=tuple(event.to_dict() for event in pool_manager.provider_events()),
            started_at=started_at,
            finished_at=finished_at,
            total_duration_ms=max(1, int((time.monotonic() - started_monotonic) * 1000)),
        )

    def run_platform_pipeline(
        self,
        plan: ExecutionPlan,
        *,
        spec: ProjectSpec,
        registry: Registry,
        retry_controller: RetryController,
        run_layout: RunLayout,
        device_count: int | None = None,
        trial_persist_callback: Callable[[TrialState, TrialExecutionSummary, TrialArtifactRecord | None], None]
        | None = None,
        trial_progress_callback: Callable[[dict[str, object]], None] | None = None,
        trial_progress_index: dict[str, int] | None = None,
        total_planned_trials: int | None = None,
    ) -> PlatformPipelineRunResult:
        self.retry_controller = retry_controller
        task_retry_controller = self._build_nonfatal_task_retry_controller(retry_controller)
        benchmark_index = {benchmark.benchmark_id: benchmark for benchmark in spec.benchmarks}
        model_index = {model.model_id: model for model in spec.models}
        plan_index = {entry.trial.trial_id: entry for entry in plan.planned_trials}
        progress_index = trial_progress_index or {
            entry.trial.trial_id: index
            for index, entry in enumerate(plan.planned_trials, start=1)
        }
        display_total_trials = total_planned_trials or len(plan.planned_trials)
        profile = next(
            profile
            for profile in spec.devices.emulator_profiles
            if profile.profile_id == spec.devices.default_profile
        )
        instance_count = device_count or max(1, spec.runtime.batch_size)
        pool_manager = create_emulator_pool_manager(
            device_mode=spec.devices.device_mode,
            adb_serials=spec.devices.adb_serials,
            avd_names=spec.devices.avd_names,
        )
        provisioned_instances = pool_manager.provision_pool(profile=profile, instance_count=instance_count)
        reset_manager = ResetManager(policy=spec.reset)
        LOGGER.info(
            "Starting platform run '%s': planned_trials=%s device_mode=%s batch_size=%s",
            plan.run_id,
            len(plan.planned_trials),
            spec.devices.device_mode.value,
            spec.runtime.batch_size,
        )
        LOGGER.info(
            "Provisioned %s emulator slot(s) for requested_parallelism=%s: %s",
            len(provisioned_instances),
            instance_count,
            ", ".join(
                (
                    f"{instance.adb_serial}"
                    f"(console={instance.console_port or 'unknown'}, "
                    f"grpc={instance.grpc_port or 'unknown'}, "
                    f"appium={instance.appium_port or 'unknown'}, "
                    f"avd={instance.avd_name or 'unknown'})"
                )
                for instance in provisioned_instances
            ) or "<none>",
        )
        if len(provisioned_instances) < instance_count:
            LOGGER.warning(
                "Requested parallelism is %s, but only %s emulator slot(s) were available. "
                "The run will use the discovered capacity.",
                instance_count,
                len(provisioned_instances),
            )

        trial_states = [
            self.state_machine.initialize(
                entry.trial,
                max_attempts=task_retry_controller.max_attempts,
            )
            for entry in plan.planned_trials
        ]
        self.scheduler.submit_trials(trial_states)
        plan.run_context.sync_scheduler_counts(self.scheduler.snapshot().to_dict())

        started_at = _utcnow()
        started_monotonic = time.monotonic()
        worker_attempts: list[WorkerLaunchOutcome] = []
        assignment_history: dict[str, list[str]] = {}
        reset_history: dict[str, list[ResetRecord]] = {}
        trial_artifacts: dict[str, TrialArtifactRecord] = {}
        trial_runtime_meta: dict[str, dict[str, object]] = {}
        execution_notes: list[str] = []
        abort_reason: str | None = None
        active_dispatches: dict[Future[_PlatformDispatchExecutionResult], object] = {}
        with ThreadPoolExecutor(max_workers=instance_count, thread_name_prefix="snowl-platform") as executor:
            while True:
                while abort_reason is None and len(active_dispatches) < instance_count:
                    dispatch = self.scheduler.poll_next_runnable_trial_with_emulator(pool_manager)
                    if dispatch is None:
                        break
                    plan_entry = plan_index[dispatch.trial_state.trial_id]
                    trial_layout = run_layout.trial_layout(dispatch.trial_state.trial_id)
                    LOGGER.info("==================================================")
                    LOGGER.info(
                        "Task %s / %s",
                        progress_index.get(dispatch.trial_state.trial_id, "?"),
                        display_total_trials,
                    )
                    LOGGER.info("trial_id: %s", dispatch.trial_state.trial_id)
                    LOGGER.info("instruction: %s", plan_entry.task.instruction or "<empty instruction>")
                    LOGGER.info("trial_dir: %s", trial_layout.trial_dir)
                    LOGGER.info("trial_log: %s", trial_layout.log_path)
                    LOGGER.info("device: %s", dispatch.emulator_lease.adb_serial)
                    LOGGER.info("==================================================")
                    LOGGER.info(
                        "[run] Task %s/%s started: %s",
                        progress_index.get(dispatch.trial_state.trial_id, "?"),
                        display_total_trials,
                        dispatch.trial_state.trial_id,
                    )
                    LOGGER.info(
                        "[run] instruction: %s",
                        plan_entry.task.instruction or "<empty instruction>",
                    )
                    LOGGER.info("[run] device: %s", dispatch.emulator_lease.adb_serial)
                    if trial_progress_callback is not None:
                        leased_instance = pool_manager.get_instance(dispatch.emulator_lease.instance_id)
                        trial_progress_callback(
                            {
                                "event": "trial_started",
                                "trial_id": dispatch.trial_state.trial_id,
                                "current_index": progress_index.get(dispatch.trial_state.trial_id, 0),
                                "total_trials": display_total_trials,
                                "instruction": plan_entry.task.instruction or "",
                                "device": dispatch.emulator_lease.adb_serial,
                                "instance_id": dispatch.emulator_lease.instance_id,
                                "attempt": dispatch.trial_state.attempt_count,
                                "console_port": leased_instance.console_port,
                                "grpc_port": leased_instance.grpc_port,
                                "appium_port": leased_instance.appium_port,
                                "avd_name": leased_instance.avd_name,
                            }
                        )
                    LOGGER.info(
                        "Dispatching trial '%s' to emulator '%s'",
                        dispatch.trial_state.trial_id,
                        dispatch.emulator_lease.instance_id,
                    )

                    benchmark = benchmark_index[dispatch.trial_state.spec.benchmark_id]
                    reset_record = reset_manager.reset_for_trial(
                        pool_manager=pool_manager,
                        lease=dispatch.emulator_lease,
                        benchmark_reset_policy=dispatch.trial_state.spec.runtime_recipe.reset_policy,
                        benchmark_requires_seed=bool(
                            benchmark.reset_requirements.get("requires_task_seed", False)
                        ),
                    )
                    LOGGER.info(
                        "Trial '%s' reset complete: strategy=%s benchmark_seed_requested=%s",
                        dispatch.trial_state.trial_id,
                        reset_record.strategy,
                        reset_record.benchmark_seed_requested,
                    )
                    assignment_history.setdefault(dispatch.trial_state.trial_id, []).append(
                        dispatch.emulator_lease.instance_id
                    )
                    reset_history.setdefault(dispatch.trial_state.trial_id, []).append(reset_record)

                    future = executor.submit(
                        self._execute_platform_dispatch,
                        dispatch=dispatch,
                        spec=spec,
                        registry=registry,
                        model_spec=model_index[dispatch.trial_state.spec.model_id],
                        plan_entry=plan_entry,
                        trial_layout=trial_layout,
                        emulator_instance=pool_manager.get_instance(dispatch.emulator_lease.instance_id),
                        retry_controller=retry_controller,
                    )
                    active_dispatches[future] = dispatch
                    plan.run_context.sync_scheduler_counts(self.scheduler.snapshot().to_dict())

                if active_dispatches:
                    done, _ = wait(tuple(active_dispatches), return_when=FIRST_COMPLETED)
                    for future in done:
                        dispatch = active_dispatches.pop(future)
                        try:
                            execution_result = future.result()
                        except Exception as error:
                            failure = self.retry_controller.classify_failure(
                                *self._classify_runtime_failure(error)
                            )
                            if self._is_run_interrupted_failure(failure):
                                LOGGER.warning(
                                    "Trial '%s' was interrupted during platform pipeline execution: %s",
                                    dispatch.trial_state.trial_id,
                                    failure.message,
                                )
                            else:
                                LOGGER.exception(
                                    "Trial '%s' failed during platform pipeline execution",
                                    dispatch.trial_state.trial_id,
                                )
                            execution_result = _PlatformDispatchExecutionResult(
                                success=False,
                                failure=failure,
                                abort_immediately=self._should_abort_run_immediately(
                                    failure.error_type,
                                    failure.message,
                                ),
                            )

                        if execution_result.worker_attempt is not None:
                            worker_attempts.append(execution_result.worker_attempt)
                        if execution_result.trial_artifact is not None:
                            trial_artifacts[dispatch.trial_state.trial_id] = execution_result.trial_artifact
                        if execution_result.runtime_meta is not None:
                            trial_runtime_meta[dispatch.trial_state.trial_id] = execution_result.runtime_meta
                        execution_notes.extend(execution_result.notes)

                        if execution_result.success:
                            self.scheduler.mark_trial_finished(dispatch.trial_state.trial_id, success=True)
                            if execution_result.worker_attempt is not None:
                                LOGGER.info(
                                    "Trial '%s' completed successfully via worker '%s'",
                                    dispatch.trial_state.trial_id,
                                    execution_result.worker_attempt.result.execution_mode,
                                )
                            elif execution_result.runtime_meta is not None:
                                execution_mode = str(
                                    execution_result.runtime_meta.get("execution_mode", "")
                                )
                                duration_ms = execution_result.runtime_meta.get("duration_ms", "?")
                                if execution_mode.startswith("bridge_"):
                                    LOGGER.info(
                                        "Trial '%s' completed successfully via bridge in %sms",
                                        dispatch.trial_state.trial_id,
                                        duration_ms,
                                    )
                                else:
                                    LOGGER.info(
                                        "Trial '%s' completed successfully via wrapped agent in %sms",
                                        dispatch.trial_state.trial_id,
                                        duration_ms,
                                    )
                        else:
                            failure = execution_result.failure or TrialFailure(
                                error_type="PAIR_RUNTIME_ERROR",
                                message="trial execution failed",
                                retryable=True,
                            )
                            if self._is_run_interrupted_failure(failure):
                                self.scheduler.mark_trial_aborted(
                                    dispatch.trial_state.trial_id,
                                    reason=failure.message,
                                    failure=failure,
                                )
                                if abort_reason is None:
                                    abort_reason = f"Run interrupted: {failure.message}"
                            else:
                                retry_decision = self.scheduler.mark_trial_finished(
                                    dispatch.trial_state.trial_id,
                                    success=False,
                                    retry_controller=None if execution_result.abort_immediately else task_retry_controller,
                                    failure=failure,
                                )
                                if execution_result.abort_immediately and abort_reason is None:
                                    abort_reason = (
                                        "Systemic runtime failure detected: "
                                        f"{failure.error_type}: {failure.message}"
                                    )
                                else:
                                    self._log_retry_decision(
                                        trial_id=dispatch.trial_state.trial_id,
                                        failure=failure,
                                        retry_decision=retry_decision,
                                    )
                        lease = self.scheduler.release_trial_lease(dispatch.trial_state.trial_id)
                        if lease is not None:
                            pool_manager.release_instance(lease)
                            LOGGER.info(
                                "Released emulator lease '%s' from trial '%s'",
                                lease.instance_id,
                                dispatch.trial_state.trial_id,
                            )
                        plan.run_context.sync_scheduler_counts(self.scheduler.snapshot().to_dict())
                        snapshot = self.scheduler.snapshot()
                        exact_counts = snapshot.exact_status_counts
                        finish_event = {
                            "event": "trial_finished",
                            "trial_id": dispatch.trial_state.trial_id,
                            "current_index": progress_index.get(dispatch.trial_state.trial_id, 0),
                            "total_trials": display_total_trials,
                            "status": dispatch.trial_state.status.value,
                            "completed": exact_counts.get(TrialStatus.COMPLETED.value, 0),
                            "failed": exact_counts.get(TrialStatus.FAILED.value, 0),
                            "aborted": exact_counts.get(TrialStatus.ABORTED.value, 0),
                            "skipped": exact_counts.get(TrialStatus.SKIPPED.value, 0),
                        }
                        LOGGER.info(
                            "[run] Task %s/%s finished: %s status=%s completed=%s failed=%s aborted=%s skipped=%s",
                            finish_event["current_index"],
                            finish_event["total_trials"],
                            finish_event["trial_id"],
                            finish_event["status"],
                            finish_event["completed"],
                            finish_event["failed"],
                            finish_event["aborted"],
                            finish_event["skipped"],
                        )
                        if trial_progress_callback is not None:
                            trial_progress_callback(finish_event)

                        if trial_persist_callback is not None:
                            trial_summary = self._build_single_platform_trial_summary(
                                trial_state=dispatch.trial_state,
                                assignment_history=assignment_history,
                                reset_history=reset_history,
                                trial_artifacts=trial_artifacts,
                                trial_runtime_meta=trial_runtime_meta,
                                worker_attempts=worker_attempts,
                            )
                            trial_persist_callback(
                                dispatch.trial_state,
                                trial_summary,
                                trial_artifacts.get(dispatch.trial_state.trial_id),
                            )

                    if abort_reason is not None and not active_dispatches:
                        if self.scheduler.has_waiting_trials():
                            aborted_trials = self._abort_remaining_trials(reason=abort_reason)
                            LOGGER.error(
                                "Aborting run '%s': %s (aborted_trials=%s)",
                                plan.run_id,
                                abort_reason,
                                aborted_trials,
                            )
                        execution_notes.append(f"Run aborted early: {abort_reason}")
                        break
                    continue

                if abort_reason is not None:
                    if self.scheduler.has_waiting_trials():
                        aborted_trials = self._abort_remaining_trials(reason=abort_reason)
                        LOGGER.error(
                            "Aborting run '%s': %s (aborted_trials=%s)",
                            plan.run_id,
                            abort_reason,
                            aborted_trials,
                        )
                    execution_notes.append(f"Run aborted early: {abort_reason}")
                    break

                if not self.scheduler.has_waiting_trials():
                    break

                abort_reason = (
                    "No healthy emulator device was available for the remaining queued trials. "
                    "Check emulator/Appium health before resuming the run."
                )
                aborted_trials = self._abort_remaining_trials(reason=abort_reason)
                LOGGER.error(
                    "Aborting run '%s': %s (aborted_trials=%s)",
                    plan.run_id,
                    abort_reason,
                    aborted_trials,
                )
                execution_notes.append(f"Run aborted early: {abort_reason}")
                break

        finished_at = _utcnow()
        final_snapshot = self.scheduler.snapshot()
        plan.run_context.sync_scheduler_counts(final_snapshot.to_dict())
        if abort_reason is not None:
            plan.run_context.status = RunStatus.ABORTED
        trial_summaries = self._build_platform_trial_summaries(
            trial_states=self.scheduler.trial_states(),
            worker_attempts=worker_attempts,
            assignment_history=assignment_history,
            reset_history=reset_history,
            plan_index=plan_index,
            trial_artifacts=trial_artifacts,
            trial_runtime_meta=trial_runtime_meta,
        )
        return PlatformPipelineRunResult(
            plan=plan,
            scheduler_snapshot=final_snapshot,
            trial_states=tuple(self.scheduler.trial_states()),
            worker_attempts=tuple(worker_attempts),
            trial_summaries=trial_summaries,
            trial_artifacts=tuple(trial_artifacts[trial_id] for trial_id in sorted(trial_artifacts)),
            reset_records=reset_manager.records(),
            pool_snapshot=pool_manager.snapshot().to_dict(),
            provider_events=tuple(event.to_dict() for event in pool_manager.provider_events()),
            started_at=started_at,
            finished_at=finished_at,
            total_duration_ms=max(1, int((time.monotonic() - started_monotonic) * 1000)),
            notes=tuple(dict.fromkeys(execution_notes)),
        )

    def _execute_platform_dispatch(
        self,
        *,
        dispatch: object,
        spec: ProjectSpec,
        registry: Registry,
        model_spec: object,
        plan_entry: object,
        trial_layout: object,
        emulator_instance: object,
        retry_controller: RetryController,
    ) -> _PlatformDispatchExecutionResult:
        bridge = None
        if dispatch.trial_state.spec.runtime_recipe.bridge_id:
            bridge = registry.instantiate_bridge(dispatch.trial_state.spec.runtime_recipe.bridge_id)

        try:
            if (
                bridge is not None
                and hasattr(bridge, "build_run_request")
                and hasattr(bridge, "run_wrapped_pair")
            ):
                LOGGER.info(
                    "Trial '%s' will run through pair bridge '%s'",
                    dispatch.trial_state.trial_id,
                    dispatch.trial_state.spec.runtime_recipe.bridge_id,
                )
                trial_layout.steps_dir.mkdir(parents=True, exist_ok=True)
                run_request = bridge.build_run_request(
                    TrialContext(
                        trial_spec=dispatch.trial_state.spec,
                        emulator_instance_id=dispatch.emulator_lease.instance_id,
                        emulator_adb_serial=dispatch.emulator_lease.adb_serial,
                        trial_output_dir=trial_layout.trial_dir,
                    ),
                    output_dir=trial_layout.trial_dir,
                    emulator_instance=emulator_instance,
                    model_spec=model_spec,
                    task_payload=plan_entry.task.payload,
                    task_instruction=plan_entry.task.instruction,
                    mock_mode=spec.devices.device_mode == DeviceMode.FAKE,
                )
                started_trial = time.monotonic()
                bridge_result = bridge.run_wrapped_pair(run_request)
                total_duration_ms = max(1, int((time.monotonic() - started_trial) * 1000))
                return _PlatformDispatchExecutionResult(
                    success=True,
                    trial_artifact=TrialArtifactRecord(
                        trial_id=dispatch.trial_state.trial_id,
                        score_bundle=bridge_result.score_bundle,
                        trajectory_steps=bridge_result.trajectory_steps,
                        raw_artifacts=bridge_result.raw_artifacts,
                        notes=bridge_result.notes,
                    ),
                    runtime_meta={
                        "duration_ms": total_duration_ms,
                        "platform_metrics": {
                            **dict(bridge_result.platform_metrics),
                            "duration_ms": int(
                                bridge_result.platform_metrics.get("duration_ms", total_duration_ms)
                            ),
                        },
                        "primary_metric": bridge_result.score_bundle.primary_metric,
                        "execution_mode": (
                            "bridge_mock" if spec.devices.device_mode == DeviceMode.FAKE else "bridge_real"
                        ),
                    },
                    notes=tuple(bridge_result.notes),
                )

            agent_adapter = registry.instantiate_agent(dispatch.trial_state.spec.agent_id)
            if (
                not dispatch.trial_state.spec.runtime_recipe.bridge_id
                and hasattr(agent_adapter, "build_run_request")
                and hasattr(agent_adapter, "run_wrapped_agent")
            ):
                LOGGER.info(
                    "Trial '%s' will run through wrapped agent '%s'",
                    dispatch.trial_state.trial_id,
                    dispatch.trial_state.spec.agent_id,
                )
                trial_layout.steps_dir.mkdir(parents=True, exist_ok=True)
                trial_artifact, runtime_meta = self._run_wrapped_agent_trial(
                    registry=registry,
                    trial_state=dispatch.trial_state,
                    plan_entry=plan_entry,
                    trial_layout=trial_layout,
                    model_spec=model_spec,
                    emulator_instance=emulator_instance,
                    mock_mode=spec.devices.device_mode == DeviceMode.FAKE,
                )
                return _PlatformDispatchExecutionResult(
                    success=True,
                    trial_artifact=trial_artifact,
                    runtime_meta=runtime_meta,
                    notes=trial_artifact.notes,
                )

            LOGGER.info(
                "Trial '%s' will run through worker mode '%s'",
                dispatch.trial_state.trial_id,
                dispatch.trial_state.spec.runtime_recipe.worker_mode.value,
            )
            outcome = self.worker_launcher.execute_trial(dispatch.trial_state)
            if outcome.result.success:
                return _PlatformDispatchExecutionResult(
                    success=True,
                    worker_attempt=outcome,
                )
            failure = outcome.result.to_trial_failure()
            LOGGER.warning(
                "Trial '%s' failed via worker '%s': %s",
                dispatch.trial_state.trial_id,
                outcome.result.execution_mode,
                outcome.result.error_message,
            )
            return _PlatformDispatchExecutionResult(
                success=False,
                worker_attempt=outcome,
                failure=failure,
                abort_immediately=self._should_abort_run_immediately(
                    failure.error_type,
                    failure.message,
                ),
            )
        except Exception as error:
            failure = self.retry_controller.classify_failure(
                *self._classify_runtime_failure(error)
            )
            if self._is_run_interrupted_failure(failure):
                LOGGER.warning(
                    "Trial '%s' was interrupted during platform pipeline execution: %s",
                    dispatch.trial_state.trial_id,
                    failure.message,
                )
            else:
                LOGGER.exception(
                    "Trial '%s' failed during platform pipeline execution",
                    dispatch.trial_state.trial_id,
                )
            return _PlatformDispatchExecutionResult(
                success=False,
                failure=failure,
                abort_immediately=self._should_abort_run_immediately(
                    failure.error_type,
                    failure.message,
                ),
            )

    def run_benchmark_probe_pipeline(
        self,
        plan: ExecutionPlan,
        *,
        spec: ProjectSpec,
        registry: Registry,
        retry_controller: RetryController,
        run_layout: RunLayout,
        operation: str,
        device_count: int | None = None,
        trial_persist_callback: Callable[[TrialState, TrialExecutionSummary, TrialArtifactRecord | None], None]
        | None = None,
        trial_progress_index: dict[str, int] | None = None,
        total_planned_trials: int | None = None,
    ) -> PlatformPipelineRunResult:
        self.retry_controller = retry_controller
        benchmark_index = {benchmark.benchmark_id: benchmark for benchmark in spec.benchmarks}
        plan_index = {entry.trial.trial_id: entry for entry in plan.planned_trials}
        progress_index = trial_progress_index or {
            entry.trial.trial_id: index
            for index, entry in enumerate(plan.planned_trials, start=1)
        }
        display_total_trials = total_planned_trials or len(plan.planned_trials)
        profile = next(
            profile
            for profile in spec.devices.emulator_profiles
            if profile.profile_id == spec.devices.default_profile
        )
        instance_count = device_count or max(1, spec.runtime.batch_size)
        pool_manager = create_emulator_pool_manager(
            device_mode=spec.devices.device_mode,
            adb_serials=spec.devices.adb_serials,
            avd_names=spec.devices.avd_names,
        )
        pool_manager.provision_pool(profile=profile, instance_count=instance_count)
        reset_manager = ResetManager(policy=spec.reset)
        LOGGER.info(
            "Starting benchmark-side run '%s': planned_trials=%s operation=%s device_mode=%s batch_size=%s",
            plan.run_id,
            len(plan.planned_trials),
            operation,
            spec.devices.device_mode.value,
            spec.runtime.batch_size,
        )

        trial_states = [
            self.state_machine.initialize(
                entry.trial,
                max_attempts=retry_controller.max_attempts,
            )
            for entry in plan.planned_trials
        ]
        self.scheduler.submit_trials(trial_states)
        plan.run_context.sync_scheduler_counts(self.scheduler.snapshot().to_dict())

        started_at = _utcnow()
        started_monotonic = time.monotonic()
        assignment_history: dict[str, list[str]] = {}
        reset_history: dict[str, list[ResetRecord]] = {}
        trial_artifacts: dict[str, TrialArtifactRecord] = {}
        trial_runtime_meta: dict[str, dict[str, object]] = {}
        execution_notes: list[str] = []
        abort_reason: str | None = None

        while True:
            dispatch = self.scheduler.poll_next_runnable_trial_with_emulator(pool_manager)
            if dispatch is None:
                if self.scheduler.has_waiting_trials():
                    abort_reason = (
                        "No healthy emulator device was available for the remaining queued trials. "
                        "Check emulator health and AndroidWorld gRPC startup before retrying."
                    )
                    aborted_trials = self._abort_remaining_trials(reason=abort_reason)
                    LOGGER.error(
                        "Aborting benchmark-side run '%s': %s (aborted_trials=%s)",
                        plan.run_id,
                        abort_reason,
                        aborted_trials,
                    )
                if abort_reason is not None:
                    execution_notes.append(f"Run aborted early: {abort_reason}")
                break

            plan_entry = plan_index[dispatch.trial_state.trial_id]
            trial_layout = run_layout.trial_layout(dispatch.trial_state.trial_id)
            LOGGER.info("==================================================")
            LOGGER.info(
                "Benchmark task %s / %s",
                progress_index.get(dispatch.trial_state.trial_id, "?"),
                display_total_trials,
            )
            LOGGER.info("trial_id: %s", dispatch.trial_state.trial_id)
            LOGGER.info("instruction: %s", plan_entry.task.instruction or "<empty instruction>")
            LOGGER.info("trial_dir: %s", trial_layout.trial_dir)
            LOGGER.info("trial_log: %s", trial_layout.log_path)
            LOGGER.info("device: %s", dispatch.emulator_lease.adb_serial)
            LOGGER.info("benchmark_operation: %s", operation)
            LOGGER.info("==================================================")

            benchmark = benchmark_index[dispatch.trial_state.spec.benchmark_id]
            reset_record = reset_manager.reset_for_trial(
                pool_manager=pool_manager,
                lease=dispatch.emulator_lease,
                benchmark_reset_policy=dispatch.trial_state.spec.runtime_recipe.reset_policy,
                benchmark_requires_seed=bool(
                    benchmark.reset_requirements.get("requires_task_seed", False)
                ),
            )
            assignment_history.setdefault(dispatch.trial_state.trial_id, []).append(
                dispatch.emulator_lease.instance_id
            )
            reset_history.setdefault(dispatch.trial_state.trial_id, []).append(reset_record)

            try:
                benchmark_adapter = registry.instantiate_benchmark(dispatch.trial_state.spec.benchmark_id)
                trial_layout.steps_dir.mkdir(parents=True, exist_ok=True)
                emulator_instance = pool_manager.get_instance(dispatch.emulator_lease.instance_id)
                probe_request = benchmark_adapter.build_probe_request(
                    TrialContext(
                        trial_spec=dispatch.trial_state.spec,
                        emulator_instance_id=dispatch.emulator_lease.instance_id,
                        emulator_adb_serial=dispatch.emulator_lease.adb_serial,
                        trial_output_dir=trial_layout.trial_dir,
                    ),
                    output_dir=trial_layout.trial_dir,
                    operation=operation,
                    task_payload=plan_entry.task.payload,
                    task_instruction=plan_entry.task.instruction,
                    emulator_instance=emulator_instance,
                    mock_mode=spec.devices.device_mode == DeviceMode.FAKE,
                )
                started_trial = time.monotonic()
                probe_result = benchmark_adapter.run_benchmark_probe(probe_request)
                total_duration_ms = max(1, int((time.monotonic() - started_trial) * 1000))
                score_bundle = probe_result.score_bundle
                platform_metrics = {
                    **dict(score_bundle.platform_metrics),
                    **{
                        key: value
                        for key, value in dict(benchmark_adapter.map_native_metrics(score_bundle.native_metrics)).items()
                        if key not in dict(score_bundle.platform_metrics)
                    },
                }
                platform_metrics.setdefault("duration_ms", total_duration_ms)
                platform_metrics.setdefault("worker_attempts", 0)
                platform_metrics.setdefault("instance_ids", [dispatch.emulator_lease.instance_id])
                platform_metrics.setdefault("reset_strategies", [reset_record.strategy])
                platform_metrics.setdefault(
                    "requested_modes",
                    [dispatch.trial_state.spec.runtime_recipe.worker_mode.value],
                )
                platform_metrics.setdefault(
                    "benchmark_seed_requested",
                    reset_record.benchmark_seed_requested,
                )
                platform_metrics.setdefault("benchmark_operation", operation)
                platform_metrics.setdefault("adb_serial", dispatch.emulator_lease.adb_serial)
                platform_metrics.setdefault(
                    "console_port",
                    getattr(emulator_instance, "console_port", 0)
                    or dispatch.trial_state.spec.runtime_recipe.ports.get(
                        "console_port",
                        int(dispatch.emulator_lease.adb_serial.removeprefix("emulator-"))
                        if dispatch.emulator_lease.adb_serial.startswith("emulator-")
                        else 0,
                    ),
                )
                platform_metrics.setdefault("grpc_port", getattr(emulator_instance, "grpc_port", 0))
                platform_metrics.setdefault("mock_mode", spec.devices.device_mode == DeviceMode.FAKE)
                trial_artifacts[dispatch.trial_state.trial_id] = TrialArtifactRecord(
                    trial_id=dispatch.trial_state.trial_id,
                    score_bundle=ScoreBundle(
                        native_metrics=dict(score_bundle.native_metrics),
                        primary_metric=score_bundle.primary_metric,
                        platform_metrics=platform_metrics,
                        notes=list(score_bundle.notes),
                    ),
                    trajectory_steps=(),
                    raw_artifacts=dict(probe_result.raw_artifacts),
                    notes=tuple(dict.fromkeys(probe_result.notes)),
                )
                trial_runtime_meta[dispatch.trial_state.trial_id] = {
                    "duration_ms": total_duration_ms,
                    "platform_metrics": platform_metrics,
                    "primary_metric": score_bundle.primary_metric,
                    "execution_mode": (
                        f"benchmark_{operation}_mock"
                        if spec.devices.device_mode == DeviceMode.FAKE
                        else f"benchmark_{operation}_real"
                    ),
                }
                execution_notes.extend(probe_result.notes)
                self.scheduler.mark_trial_finished(dispatch.trial_state.trial_id, success=True)
                LOGGER.info(
                    "Trial '%s' completed successfully via benchmark-side operation '%s' in %sms",
                    dispatch.trial_state.trial_id,
                    operation,
                    total_duration_ms,
                )
            except Exception as error:
                failure = self.retry_controller.classify_failure(
                    *self._classify_runtime_failure(error)
                )
                if self._is_run_interrupted_failure(failure):
                    LOGGER.warning(
                        "Trial '%s' was interrupted during benchmark-side operation '%s': %s",
                        dispatch.trial_state.trial_id,
                        operation,
                        failure.message,
                    )
                else:
                    LOGGER.exception(
                        "Trial '%s' failed during benchmark-side operation '%s'",
                        dispatch.trial_state.trial_id,
                        operation,
                    )
                abort_immediately = self._should_abort_run_immediately(
                    failure.error_type,
                    failure.message,
                )
                if self._is_run_interrupted_failure(failure):
                    self.scheduler.mark_trial_aborted(
                        dispatch.trial_state.trial_id,
                        reason=failure.message,
                        failure=failure,
                    )
                    abort_reason = f"Run interrupted: {failure.message}"
                else:
                    retry_decision = self.scheduler.mark_trial_finished(
                        dispatch.trial_state.trial_id,
                        success=False,
                        retry_controller=None if abort_immediately else retry_controller,
                        failure=failure,
                    )
                    if abort_immediately:
                        abort_reason = (
                            "Systemic runtime failure detected: "
                            f"{failure.error_type}: {failure.message}"
                        )
                    else:
                        self._log_retry_decision(
                            trial_id=dispatch.trial_state.trial_id,
                            failure=failure,
                            retry_decision=retry_decision,
                        )
            lease = self.scheduler.release_trial_lease(dispatch.trial_state.trial_id)
            if lease is not None:
                pool_manager.release_instance(lease)
            plan.run_context.sync_scheduler_counts(self.scheduler.snapshot().to_dict())

            if trial_persist_callback is not None:
                trial_summary = self._build_single_platform_trial_summary(
                    trial_state=dispatch.trial_state,
                    assignment_history=assignment_history,
                    reset_history=reset_history,
                    trial_artifacts=trial_artifacts,
                    trial_runtime_meta=trial_runtime_meta,
                    worker_attempts=[],
                )
                trial_persist_callback(
                    dispatch.trial_state,
                    trial_summary,
                    trial_artifacts.get(dispatch.trial_state.trial_id),
                )

            if abort_reason is not None:
                aborted_trials = self._abort_remaining_trials(reason=abort_reason)
                LOGGER.error(
                    "Aborting benchmark-side run '%s': %s (aborted_trials=%s)",
                    plan.run_id,
                    abort_reason,
                    aborted_trials,
                )
                execution_notes.append(f"Run aborted early: {abort_reason}")
                break

        finished_at = _utcnow()
        final_snapshot = self.scheduler.snapshot()
        plan.run_context.sync_scheduler_counts(final_snapshot.to_dict())
        if abort_reason is not None:
            plan.run_context.status = RunStatus.ABORTED
        trial_summaries = self._build_platform_trial_summaries(
            trial_states=self.scheduler.trial_states(),
            worker_attempts=[],
            assignment_history=assignment_history,
            reset_history=reset_history,
            plan_index=plan_index,
            trial_artifacts=trial_artifacts,
            trial_runtime_meta=trial_runtime_meta,
        )
        notes = list(dict.fromkeys(execution_notes))
        notes.append(
            "Executed through the benchmark-side platform probe path without an external agent bridge."
        )
        if operation != "setup":
            notes.append(
                "No external agent actions were executed, so task_success can remain 0 even when the benchmark bootstrap succeeded."
            )
        return PlatformPipelineRunResult(
            plan=plan,
            scheduler_snapshot=final_snapshot,
            trial_states=tuple(self.scheduler.trial_states()),
            worker_attempts=(),
            trial_summaries=trial_summaries,
            trial_artifacts=tuple(trial_artifacts[trial_id] for trial_id in sorted(trial_artifacts)),
            reset_records=reset_manager.records(),
            pool_snapshot=pool_manager.snapshot().to_dict(),
            provider_events=tuple(event.to_dict() for event in pool_manager.provider_events()),
            started_at=started_at,
            finished_at=finished_at,
            total_duration_ms=max(1, int((time.monotonic() - started_monotonic) * 1000)),
            notes=tuple(dict.fromkeys(notes)),
        )

    def _abort_remaining_trials(self, *, reason: str) -> int:
        aborted = 0
        for trial_state in self.scheduler.trial_states():
            if trial_state.status in {
                TrialStatus.SCHEDULED,
                TrialStatus.RETRY_WAITING,
            }:
                self.state_machine.abort(trial_state, reason=reason)
                aborted += 1
        return aborted

    def _build_nonfatal_task_retry_controller(
        self,
        retry_controller: RetryController,
    ) -> RetryController:
        policy = retry_controller.policy
        return RetryController(
            RetryPolicy(
                max_trial_retries=max(policy.max_trial_retries, MIN_NON_FATAL_TRIAL_RETRIES),
                max_step_retries=policy.max_step_retries,
                backoff_sec=policy.backoff_sec,
                retry_on=tuple(dict.fromkeys((*policy.retry_on, *NON_FATAL_TASK_RETRYABLE_ERRORS))),
            )
        )

    def _should_abort_run_immediately(self, error_type: str, message: str) -> bool:
        lowered = message.lower()
        return (
            error_type == "RUN_INTERRUPTED"
            or self._is_model_runtime_failure(error_type, lowered)
            or self._is_device_runtime_failure(error_type, lowered)
            or self._is_wrapped_agent_runtime_timeout(error_type, lowered)
            or self._is_androidworld_runtime_failure(error_type, lowered)
        )

    def _is_run_interrupted_failure(self, failure: TrialFailure) -> bool:
        lowered = failure.message.lower()
        return failure.error_type == "RUN_INTERRUPTED" or "keyboardinterrupt" in lowered

    def _is_model_runtime_failure(self, error_type: str, message: str) -> bool:
        if error_type == "MODEL_CALL_FAILED":
            return True
        model_markers = (
            "model error:",
            "chat.completions",
            "chat/completions",
            "api key",
            "authentication",
            "unauthorized",
            "rate limit",
            "quota exceeded",
            "connection error",
            "connection timed out",
            "read timeout",
            "provider returned status",
            "cannot connect to",
            "could not reach the configured model endpoint",
        )
        return any(marker in message for marker in model_markers)

    def _is_device_runtime_failure(self, error_type: str, message: str) -> bool:
        if error_type == "DEVICE_NOT_FOUND":
            return True
        if error_type in {"ADB_BACKEND_ERROR", "BENCHMARK_RUN_FAILED", "PAIR_RUNTIME_ERROR"} and self._looks_like_mobilesafetybench_bootstrap_device_failure(message):
            return True
        device_markers = (
            "device not found",
            "device offline",
            "no devices/emulators found",
            "disappeared during execution",
            "emulator was killed",
            "emulator exited",
            "emulator quit",
            "adb serial",
        )
        failure_suffixes = ("not found", "offline", "disappeared", "lost", "killed", "quit", "exited")
        return error_type == "ADB_BACKEND_ERROR" and any(marker in message for marker in device_markers) and any(
            suffix in message for suffix in failure_suffixes
        )

    def _looks_like_mobilesafetybench_bootstrap_device_failure(self, message: str) -> bool:
        return (
            "benchmark bootstrap" in message
            and (
                "timed out waiting for the leased emulator to become ready" in message
                or "wait-for-device failed" in message
                or "sys.boot_completed failed" in message
                or "wm size returned unexpected output" in message
                or "adb get-state returned" in message
            )
        )

    def _is_wrapped_agent_runtime_timeout(self, error_type: str, message: str) -> bool:
        if error_type not in {"AGENT_WORKER_CRASH", "PAIR_RUNTIME_ERROR", "BENCHMARK_RUN_FAILED"}:
            return False
        return (
            "timeoutexpired" in message
            and "timed out after" in message
            and (
                "runtime invocation failed inside the pair bridge" in message
                or "mobile_agent_v3_5_runner" in message
                or "mobile_agent_e_runner" in message
                or "open_autoglm" in message and "_runner" in message
            )
        )

    def _is_androidworld_runtime_failure(self, error_type: str, message: str) -> bool:
        if error_type not in {"BENCHMARK_RUN_FAILED", "PAIR_RUNTIME_ERROR", "AGENT_WORKER_CRASH", "ADB_BACKEND_ERROR"}:
            return False
        markers = (
            "androidworld could not connect to the emulator runtime",
            "androidworld accessibility runtime became unavailable",
            "accessibility forwarder",
            "could not get a11y tree",
            "accessibility tree became unavailable",
        )
        return any(marker in message for marker in markers)

    def _log_retry_decision(
        self,
        *,
        trial_id: str,
        failure: TrialFailure,
        retry_decision: object,
    ) -> None:
        if retry_decision is None:
            LOGGER.warning(
                "Trial '%s' failed without scheduling a retry: %s: %s",
                trial_id,
                failure.error_type,
                failure.message,
            )
            return
        if getattr(retry_decision, "should_retry", False):
            LOGGER.warning(
                "Trial '%s' failed with %s and will retry (attempt %s/%s): %s",
                trial_id,
                failure.error_type,
                getattr(retry_decision, "next_attempt", "?"),
                getattr(retry_decision, "max_attempts", "?"),
                failure.message,
            )
            return
        LOGGER.warning(
            "Trial '%s' failed with %s and exhausted retry budget after %s attempt(s): %s",
            trial_id,
            failure.error_type,
            getattr(retry_decision, "max_attempts", "?"),
            failure.message,
        )

    def _run_wrapped_agent_trial(
        self,
        *,
        registry: Registry,
        trial_state: TrialState,
        plan_entry: object,
        trial_layout: object,
        model_spec: object,
        emulator_instance: object,
        mock_mode: bool,
    ) -> tuple[TrialArtifactRecord, dict[str, object]]:
        agent_adapter = registry.instantiate_agent(trial_state.spec.agent_id)
        benchmark_adapter = registry.instantiate_benchmark(trial_state.spec.benchmark_id)
        trial_context = TrialContext(
            trial_spec=trial_state.spec,
            emulator_instance_id=getattr(emulator_instance, "instance_id", ""),
            emulator_adb_serial=getattr(emulator_instance, "adb_serial", ""),
            trial_output_dir=trial_layout.trial_dir,
        )
        benchmark_raw_artifacts: dict[str, str] = {}
        try:
            try:
                benchmark_adapter.prepare_trial(trial_context)
                benchmark_adapter.seed_environment(trial_context)
                observation = benchmark_adapter.get_initial_observation(trial_context)
                benchmark_raw_artifacts = benchmark_adapter.capture_raw_artifacts(trial_context)
            except Exception as error:
                raise RuntimeError(
                    f"MobileSafetyBench task invocation failed: {error}"
                ) from error
            run_request = agent_adapter.build_run_request(
                trial_context,
                output_dir=trial_layout.trial_dir,
                observation=observation,
                task_instruction=getattr(plan_entry.task, "instruction", ""),
                model_spec=model_spec,
                emulator_instance=emulator_instance,
                task_payload=getattr(plan_entry.task, "payload", {}),
                mock_mode=mock_mode,
            )
            started_trial = time.monotonic()
            agent_result = agent_adapter.run_wrapped_agent(run_request)
            total_duration_ms = max(1, int((time.monotonic() - started_trial) * 1000))
        finally:
            try:
                benchmark_adapter.cleanup_trial(trial_context)
            except Exception:
                LOGGER.warning(
                    "Benchmark cleanup raised after trial '%s'",
                    trial_state.trial_id,
                    exc_info=True,
                )

        score_bundle = self._build_wrapped_agent_score_bundle(
            benchmark_adapter=benchmark_adapter,
            agent_result=agent_result,
            duration_ms=total_duration_ms,
        )
        notes = tuple(dict.fromkeys(score_bundle.notes))
        trial_artifact = TrialArtifactRecord(
            trial_id=trial_state.trial_id,
            score_bundle=score_bundle,
            trajectory_steps=tuple(getattr(agent_result, "trajectory_steps", ()) or ()),
            raw_artifacts={
                **{f"benchmark_{key}": value for key, value in benchmark_raw_artifacts.items()},
                **dict(getattr(agent_result, "raw_artifacts", {})),
            },
            notes=notes,
        )
        return (
            trial_artifact,
            {
                "duration_ms": total_duration_ms,
                "platform_metrics": {
                    **dict(score_bundle.platform_metrics),
                    "duration_ms": int(
                        score_bundle.platform_metrics.get("duration_ms", total_duration_ms)
                    ),
                },
                "primary_metric": score_bundle.primary_metric,
                "execution_mode": "wrapped_agent_mock" if mock_mode else "wrapped_agent_real",
            },
        )

    def _build_wrapped_agent_score_bundle(
        self,
        *,
        benchmark_adapter: object,
        agent_result: object,
        duration_ms: int,
    ) -> ScoreBundle:
        native_metrics = dict(getattr(agent_result, "native_metrics", {}) or {})
        mapped_platform_metrics = (
            dict(benchmark_adapter.map_native_metrics(native_metrics))
            if native_metrics and hasattr(benchmark_adapter, "map_native_metrics")
            else {}
        )
        platform_metrics = {
            **mapped_platform_metrics,
            **dict(getattr(agent_result, "platform_metrics", {}) or {}),
        }
        platform_metrics.setdefault("duration_ms", duration_ms)
        primary_value = mapped_platform_metrics.get(
            "task_success",
            platform_metrics.get("finished", False),
        )
        notes = list(dict.fromkeys([
            *tuple(getattr(agent_result, "notes", ()) or ()),
            "Executed through the platform wrapped-agent path without a pair bridge.",
            "Benchmark-native scoring remains provisional until a dedicated pair bridge is implemented.",
        ]))
        return ScoreBundle(
            native_metrics=native_metrics,
            primary_metric=self._coerce_primary_metric(primary_value),
            platform_metrics=platform_metrics,
            notes=notes,
        )

    def _coerce_primary_metric(self, value: object) -> int:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        return int(bool(value))

    def _build_single_platform_trial_summary(
        self,
        *,
        trial_state: TrialState,
        assignment_history: dict[str, list[str]],
        reset_history: dict[str, list[ResetRecord]],
        trial_artifacts: dict[str, TrialArtifactRecord],
        trial_runtime_meta: dict[str, dict[str, object]],
        worker_attempts: list[WorkerLaunchOutcome],
    ) -> TrialExecutionSummary:
        reset_records = reset_history.get(trial_state.trial_id, [])
        instance_ids = tuple(dict.fromkeys(assignment_history.get(trial_state.trial_id, [])))
        reset_strategies = tuple(dict.fromkeys(record.strategy for record in reset_records))
        benchmark_seed_requested = any(record.benchmark_seed_requested for record in reset_records)
        direct_artifact = trial_artifacts.get(trial_state.trial_id)
        if direct_artifact is not None:
            runtime_meta = trial_runtime_meta.get(trial_state.trial_id, {})
            platform_metrics = dict(
                runtime_meta.get("platform_metrics", direct_artifact.score_bundle.platform_metrics)
            )
            total_duration_ms = int(runtime_meta.get("duration_ms", platform_metrics.get("duration_ms", 0)))
            execution_mode = str(runtime_meta.get("execution_mode", "bridge"))
            return TrialExecutionSummary(
                trial_id=trial_state.trial_id,
                task_id=trial_state.spec.task_id,
                agent_id=trial_state.spec.agent_id,
                benchmark_id=trial_state.spec.benchmark_id,
                status=trial_state.status.value,
                attempt_count=trial_state.attempt_count,
                total_duration_ms=total_duration_ms,
                worker_attempts=0,
                execution_modes=(execution_mode,),
                requested_modes=(trial_state.spec.runtime_recipe.worker_mode.value,),
                instance_ids=instance_ids,
                reset_strategies=reset_strategies,
                benchmark_seed_requested=benchmark_seed_requested,
                primary_metric=self._coerce_primary_metric(
                    runtime_meta.get("primary_metric", direct_artifact.score_bundle.primary_metric)
                ),
                platform_metrics=platform_metrics,
                last_error_type=trial_state.last_error_type,
                last_error_message=trial_state.last_error_message,
            )

        attempts = [outcome for outcome in worker_attempts if outcome.result.trial_id == trial_state.trial_id]
        total_duration_ms = sum(outcome.result.duration_ms for outcome in attempts)
        execution_modes = tuple(dict.fromkeys(outcome.result.execution_mode for outcome in attempts))
        requested_modes = tuple(dict.fromkeys(outcome.result.requested_mode for outcome in attempts))
        primary_metric = 1 if trial_state.status.value == "COMPLETED" else 0
        return TrialExecutionSummary(
            trial_id=trial_state.trial_id,
            task_id=trial_state.spec.task_id,
            agent_id=trial_state.spec.agent_id,
            benchmark_id=trial_state.spec.benchmark_id,
            status=trial_state.status.value,
            attempt_count=trial_state.attempt_count,
            total_duration_ms=total_duration_ms,
            worker_attempts=len(attempts),
            execution_modes=execution_modes,
            requested_modes=requested_modes,
            instance_ids=instance_ids,
            reset_strategies=reset_strategies,
            benchmark_seed_requested=benchmark_seed_requested,
            primary_metric=primary_metric,
            platform_metrics={
                "duration_ms": total_duration_ms,
                "worker_attempts": len(attempts),
                "instance_ids": list(instance_ids),
                "reset_strategies": list(reset_strategies),
                "requested_modes": list(requested_modes),
            },
            last_error_type=trial_state.last_error_type,
            last_error_message=trial_state.last_error_message,
        )

    def _build_trial_summaries(
        self,
        *,
        trial_states: list[TrialState],
        worker_attempts: list[WorkerLaunchOutcome],
        assignment_history: dict[str, list[str]],
        reset_history: dict[str, list[ResetRecord]],
    ) -> tuple[TrialExecutionSummary, ...]:
        attempts_by_trial: dict[str, list[WorkerLaunchOutcome]] = {}
        for outcome in worker_attempts:
            attempts_by_trial.setdefault(outcome.result.trial_id, []).append(outcome)

        summaries: list[TrialExecutionSummary] = []
        for trial_state in trial_states:
            attempts = attempts_by_trial.get(trial_state.trial_id, [])
            reset_records = reset_history.get(trial_state.trial_id, [])
            total_duration_ms = sum(outcome.result.duration_ms for outcome in attempts)
            execution_modes = tuple(dict.fromkeys(outcome.result.execution_mode for outcome in attempts))
            requested_modes = tuple(dict.fromkeys(outcome.result.requested_mode for outcome in attempts))
            instance_ids = tuple(dict.fromkeys(assignment_history.get(trial_state.trial_id, [])))
            reset_strategies = tuple(dict.fromkeys(record.strategy for record in reset_records))
            benchmark_seed_requested = any(record.benchmark_seed_requested for record in reset_records)
            primary_metric = 1 if trial_state.status.value == "COMPLETED" else 0
            summaries.append(
                TrialExecutionSummary(
                    trial_id=trial_state.trial_id,
                    task_id=trial_state.spec.task_id,
                    agent_id=trial_state.spec.agent_id,
                    benchmark_id=trial_state.spec.benchmark_id,
                    status=trial_state.status.value,
                    attempt_count=trial_state.attempt_count,
                    total_duration_ms=total_duration_ms,
                    worker_attempts=len(attempts),
                    execution_modes=execution_modes,
                    requested_modes=requested_modes,
                    instance_ids=instance_ids,
                    reset_strategies=reset_strategies,
                    benchmark_seed_requested=benchmark_seed_requested,
                    primary_metric=primary_metric,
                    platform_metrics={
                        "duration_ms": total_duration_ms,
                        "worker_attempts": len(attempts),
                        "instance_ids": list(instance_ids),
                        "reset_strategies": list(reset_strategies),
                        "requested_modes": list(requested_modes),
                    },
                    last_error_type=trial_state.last_error_type,
                    last_error_message=trial_state.last_error_message,
                )
            )
        return tuple(summaries)

    def _build_platform_trial_summaries(
        self,
        *,
        trial_states: list[TrialState],
        worker_attempts: list[WorkerLaunchOutcome],
        assignment_history: dict[str, list[str]],
        reset_history: dict[str, list[ResetRecord]],
        plan_index: dict[str, object],
        trial_artifacts: dict[str, TrialArtifactRecord],
        trial_runtime_meta: dict[str, dict[str, object]],
    ) -> tuple[TrialExecutionSummary, ...]:
        attempts_by_trial: dict[str, list[WorkerLaunchOutcome]] = {}
        for outcome in worker_attempts:
            attempts_by_trial.setdefault(outcome.result.trial_id, []).append(outcome)

        summaries: list[TrialExecutionSummary] = []
        for trial_state in trial_states:
            summaries.append(
                self._build_single_platform_trial_summary(
                    trial_state=trial_state,
                    assignment_history=assignment_history,
                    reset_history=reset_history,
                    trial_artifacts=trial_artifacts,
                    trial_runtime_meta=trial_runtime_meta,
                    worker_attempts=attempts_by_trial.get(trial_state.trial_id, []),
                )
            )
        return tuple(summaries)

    def _classify_runtime_failure(self, error: Exception) -> tuple[str, str]:
        message = str(error)
        lowered = message.lower()
        if "keyboardinterrupt" in lowered:
            return "RUN_INTERRUPTED", message
        if (
            "require these environment variables" in lowered
            or "required to persist bridge screenshot" in lowered
            or "upstream runtime import preflight failed" in lowered
            or "install the upstream requirements" in lowered
            or "requires these python packages" in lowered
            or "could not find the configured adb executable" in lowered
        ):
            return "RUNTIME_PREREQUISITE_MISSING", message
        if "image input" in lowered or "model" in lowered and "require" in lowered:
            return "MODEL_INCOMPATIBLE", message
        if (
            "model error:" in lowered
            or "chat.completions" in lowered
            or "chat/completions" in lowered
            or "authentication" in lowered
            or "unauthorized" in lowered
            or "rate limit" in lowered
            or "quota exceeded" in lowered
            or "cannot connect to" in lowered
            or "connection timed out" in lowered
            or "connection error" in lowered
            or "connection aborted" in lowered
            or "read timeout" in lowered
            or "returned no response" in lowered
            or "could not reach the configured model endpoint" in lowered
        ):
            return "MODEL_CALL_FAILED", message
        if self._looks_like_mobilesafetybench_bootstrap_device_failure(lowered):
            return "ADB_BACKEND_ERROR", message
        if self._is_wrapped_agent_runtime_timeout("AGENT_WORKER_CRASH", lowered):
            return "AGENT_WORKER_CRASH", message
        if (
            "no running android emulator" in lowered
            or "adb serial" in lowered and ("disappeared" in lowered or "not found" in lowered)
            or "no devices/emulators found" in lowered
            or "device not found" in lowered
            or "device offline" in lowered
            or "disappeared during execution" in lowered
            or "no running" in lowered
            or "no adb device detected" in lowered
        ):
            return "DEVICE_NOT_FOUND", message
        if (
            "androidworld accessibility runtime became unavailable" in lowered
            or "could not get a11y tree" in lowered
            or "accessibility forwarder" in lowered
            or "androidworld could not connect to the emulator runtime" in lowered
        ):
            return "BENCHMARK_RUN_FAILED", message
        if any(
            marker in lowered
            for marker in (
                "appium",
                "emulator exited",
                "emulator quit",
                "emulator was killed",
                "adb devices",
                "adb shell",
                "adb executable",
            )
        ):
            return "ADB_BACKEND_ERROR", message
        if (
            "open-autoglm" in lowered
            or "phone_agent" in lowered
            or "model response" in lowered
            or "mobile-agent-e wrapped subprocess failed" in lowered
        ):
            return "AGENT_WORKER_CRASH", message
        if "mobilesafetybench" in lowered or "benchmark" in lowered:
            return "BENCHMARK_RUN_FAILED", message
        return "PAIR_RUNTIME_ERROR", message
