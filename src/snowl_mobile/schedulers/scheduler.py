from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from snowl_mobile.core.errors import SchedulerError
from snowl_mobile.core.states import TrialStatus
from snowl_mobile.core.trial_state_machine import TrialState, TrialStateMachine
from snowl_mobile.devices.emulator_instance import EmulatorLease
from snowl_mobile.devices.emulator_pool import EmulatorPoolManager
from snowl_mobile.schedulers.retry_controller import RetryController, RetryDecision, TrialFailure


@dataclass(frozen=True, slots=True)
class SchedulerSnapshot:
    queued: int
    running: int
    succeeded: int
    failed: int
    skipped: int
    retrying: int
    exact_status_counts: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        return {
            "queued": self.queued,
            "running": self.running,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "skipped": self.skipped,
            "retrying": self.retrying,
            "exact_status_counts": self.exact_status_counts,
        }


@dataclass(frozen=True, slots=True)
class ScheduledTrialLease:
    trial_state: TrialState
    emulator_lease: EmulatorLease


class Scheduler:
    def __init__(self, *, state_machine: TrialStateMachine | None = None) -> None:
        self.state_machine = state_machine or TrialStateMachine()
        self._trials: dict[str, TrialState] = {}
        self._queue: deque[str] = deque()
        self._running: set[str] = set()
        self._leases: dict[str, EmulatorLease] = {}

    def submit_trial(self, trial_state: TrialState) -> None:
        if trial_state.trial_id in self._trials:
            raise SchedulerError(f"trial '{trial_state.trial_id}' was already submitted")
        self._trials[trial_state.trial_id] = trial_state
        self.state_machine.queue(trial_state, reason="submitted to scheduler")
        self._queue.append(trial_state.trial_id)

    def submit_trials(self, trial_states: list[TrialState]) -> None:
        for trial_state in trial_states:
            self.submit_trial(trial_state)

    def poll_next_runnable_trial(self) -> TrialState | None:
        while self._queue:
            trial_id = self._queue.popleft()
            trial_state = self._trials[trial_id]
            if trial_state.status != TrialStatus.SCHEDULED:
                continue
            self.state_machine.start(trial_state, reason="scheduler dispatched")
            self._running.add(trial_id)
            return trial_state
        return None

    def poll_next_runnable_trial_with_emulator(
        self,
        pool_manager: EmulatorPoolManager,
    ) -> ScheduledTrialLease | None:
        queue_length = len(self._queue)
        for _ in range(queue_length):
            trial_id = self._queue.popleft()
            trial_state = self._trials[trial_id]
            if trial_state.status != TrialStatus.SCHEDULED:
                continue
            lease = pool_manager.assign_trial(trial_state.spec)
            if lease is None:
                self._queue.append(trial_id)
                continue
            self.state_machine.start(trial_state, reason="scheduler dispatched with emulator")
            self._running.add(trial_id)
            self._leases[trial_id] = lease
            return ScheduledTrialLease(trial_state=trial_state, emulator_lease=lease)
        return None

    def mark_trial_finished(
        self,
        trial_id: str,
        *,
        success: bool,
        retry_controller: RetryController | None = None,
        failure: TrialFailure | None = None,
    ) -> RetryDecision | None:
        trial_state = self._require_trial(trial_id)
        self._running.discard(trial_id)
        if success:
            self.state_machine.complete(trial_state, reason="trial completed successfully")
            return None

        if failure is None:
            raise SchedulerError("failure details are required when marking a trial as unsuccessful")
        self.state_machine.fail(
            trial_state,
            error_type=failure.error_type,
            error_message=failure.message,
            reason=failure.message,
        )
        if retry_controller is None:
            return None
        decision = retry_controller.should_retry(trial_state, failure)
        if decision.should_retry:
            self.retry_failed_trial(trial_id, reason=decision.reason)
        return decision

    def retry_failed_trial(self, trial_id: str, *, reason: str) -> TrialState:
        trial_state = self._require_trial(trial_id)
        if trial_state.status != TrialStatus.FAILED:
            raise SchedulerError(f"trial '{trial_id}' is not in FAILED status")
        self.state_machine.mark_retry_waiting(trial_state, reason=reason)
        self.state_machine.queue(trial_state, reason=reason)
        self._queue.append(trial_id)
        return trial_state

    def mark_trial_skipped(self, trial_id: str, *, reason: str) -> TrialState:
        trial_state = self._require_trial(trial_id)
        self._running.discard(trial_id)
        self.state_machine.skip(trial_state, reason=reason)
        return trial_state

    def release_trial_lease(self, trial_id: str) -> EmulatorLease | None:
        return self._leases.pop(trial_id, None)

    def active_lease(self, trial_id: str) -> EmulatorLease | None:
        return self._leases.get(trial_id)

    def has_waiting_trials(self) -> bool:
        return any(trial_state.status == TrialStatus.SCHEDULED for trial_state in self._trials.values())

    def snapshot(self) -> SchedulerSnapshot:
        exact = {status.value: 0 for status in TrialStatus}
        for trial_state in self._trials.values():
            exact[trial_state.status.value] += 1
        return SchedulerSnapshot(
            queued=exact[TrialStatus.SCHEDULED.value],
            running=exact[TrialStatus.PREPARING.value]
            + exact[TrialStatus.RUNNING.value]
            + exact[TrialStatus.SCORING.value],
            succeeded=exact[TrialStatus.COMPLETED.value],
            failed=exact[TrialStatus.FAILED.value],
            skipped=exact[TrialStatus.SKIPPED.value],
            retrying=exact[TrialStatus.RETRY_WAITING.value],
            exact_status_counts=exact,
        )

    def trial_states(self) -> list[TrialState]:
        return [self._trials[trial_id] for trial_id in sorted(self._trials)]

    def _require_trial(self, trial_id: str) -> TrialState:
        try:
            return self._trials[trial_id]
        except KeyError as error:
            raise SchedulerError(f"unknown trial '{trial_id}'") from error
