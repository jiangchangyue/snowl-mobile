from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from snowl_mobile.core.errors import (
    WorkerCrashError,
    WorkerProtocolError,
    WorkerTimeoutError,
)
from snowl_mobile.core.trial_state_machine import TrialState
from snowl_mobile.runtime.worker_protocol import WorkerResult, WorkerRunRequest, WorkerSpec
from snowl_mobile.runtime.worker_transport import (
    InProcessWorkerTransport,
    SubprocessWorkerTransport,
    WorkerTransport,
)


def _utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class WorkerLaunchOutcome:
    worker_spec: WorkerSpec
    result: WorkerResult


class WorkerLauncher:
    def __init__(self, *, cwd: Path | None = None) -> None:
        self.cwd = cwd or Path.cwd()

    def build_worker_spec(
        self,
        trial_state: TrialState,
        *,
        startup_timeout_sec: int = 5,
        trial_timeout_sec: int | None = None,
    ) -> WorkerSpec:
        return WorkerSpec.from_trial_spec(
            trial_state.spec,
            startup_timeout_sec=startup_timeout_sec,
            trial_timeout_sec=trial_timeout_sec,
            cwd=self.cwd,
        )

    def execute_trial(
        self,
        trial_state: TrialState,
        *,
        startup_timeout_sec: int = 5,
        trial_timeout_sec: int | None = None,
    ) -> WorkerLaunchOutcome:
        worker_spec = self.build_worker_spec(
            trial_state,
            startup_timeout_sec=startup_timeout_sec,
            trial_timeout_sec=trial_timeout_sec,
        )
        transport = self._transport_for_spec(worker_spec)
        started_at = _utcnow()
        try:
            handshake = transport.initialize(worker_spec)
            request = WorkerRunRequest.from_trial_state(
                trial_state.spec,
                attempt=trial_state.attempt_count,
            )
            result = transport.run_trial(request)
            if result.worker_pid is None and handshake.worker_pid is not None:
                result = WorkerResult.from_mapping(
                    {
                        **result.to_dict(),
                        "worker_pid": handshake.worker_pid,
                    }
                )
            return WorkerLaunchOutcome(worker_spec=worker_spec, result=result)
        except WorkerTimeoutError as error:
            return WorkerLaunchOutcome(
                worker_spec=worker_spec,
                result=WorkerResult.failure_result(
                    worker_id=worker_spec.worker_id,
                    trial_id=trial_state.trial_id,
                    execution_mode=worker_spec.execution_mode,
                    requested_mode=worker_spec.requested_mode,
                    attempt=trial_state.attempt_count,
                    error_type="WORKER_TIMEOUT",
                    error_message=str(error),
                    retryable=True,
                    started_at=started_at,
                    finished_at=_utcnow(),
                ),
            )
        except WorkerCrashError as error:
            return WorkerLaunchOutcome(
                worker_spec=worker_spec,
                result=WorkerResult.failure_result(
                    worker_id=worker_spec.worker_id,
                    trial_id=trial_state.trial_id,
                    execution_mode=worker_spec.execution_mode,
                    requested_mode=worker_spec.requested_mode,
                    attempt=trial_state.attempt_count,
                    error_type="WORKER_CRASH",
                    error_message=str(error),
                    retryable=True,
                    started_at=started_at,
                    finished_at=_utcnow(),
                ),
            )
        except WorkerProtocolError as error:
            return WorkerLaunchOutcome(
                worker_spec=worker_spec,
                result=WorkerResult.failure_result(
                    worker_id=worker_spec.worker_id,
                    trial_id=trial_state.trial_id,
                    execution_mode=worker_spec.execution_mode,
                    requested_mode=worker_spec.requested_mode,
                    attempt=trial_state.attempt_count,
                    error_type="WORKER_PROTOCOL_ERROR",
                    error_message=str(error),
                    retryable=True,
                    started_at=started_at,
                    finished_at=_utcnow(),
                ),
            )
        finally:
            transport.close()

    def _transport_for_spec(self, worker_spec: WorkerSpec) -> WorkerTransport:
        if worker_spec.execution_mode == "in_process":
            return InProcessWorkerTransport()
        if worker_spec.execution_mode == "subprocess":
            return SubprocessWorkerTransport()
        raise WorkerProtocolError(
            f"unsupported execution mode '{worker_spec.execution_mode}'"
        )
