from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from snowl_mobile.adapters.builtin import create_builtin_registry
from snowl_mobile.runtime.worker_protocol import (
    WORKER_PROTOCOL_VERSION,
    WorkerHandshake,
    WorkerResult,
    WorkerRunRequest,
    WorkerSpec,
)


def _utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class DummyWorkerService:
    """Small shared worker service used by both in-process and subprocess modes."""

    def __init__(self) -> None:
        self._registry = create_builtin_registry()
        self._worker_spec: WorkerSpec | None = None

    def initialize(self, worker_spec: WorkerSpec) -> WorkerHandshake:
        self._worker_spec = worker_spec
        return WorkerHandshake(
            worker_id=worker_spec.worker_id,
            execution_mode=worker_spec.execution_mode,
            requested_mode=worker_spec.requested_mode,
            protocol_version=WORKER_PROTOCOL_VERSION,
            worker_pid=os.getpid(),
            started_at=_utcnow(),
        )

    def run_trial(self, request: WorkerRunRequest) -> WorkerResult:
        worker_spec = self._require_worker_spec()
        started_at = _utcnow()
        started_monotonic = time.monotonic()
        behavior = self._resolve_behavior(request)

        if behavior == "crash":
            raise RuntimeError("simulated worker crash")
        if behavior == "timeout":
            time.sleep(max(worker_spec.trial_timeout_sec + 1, 2))

        agent_adapter = self._registry.instantiate_agent(request.trial.agent_id)
        benchmark_adapter = self._registry.instantiate_benchmark(request.trial.benchmark_id)
        agent_spec = agent_adapter.describe()
        benchmark_spec = benchmark_adapter.describe()

        if behavior == "retry_once" and request.attempt == 1:
            finished_at = _utcnow()
            return WorkerResult.failure_result(
                worker_id=worker_spec.worker_id,
                trial_id=request.trial.trial_id,
                execution_mode=worker_spec.execution_mode,
                requested_mode=worker_spec.requested_mode,
                attempt=request.attempt,
                worker_pid=os.getpid(),
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=max(1, int((time.monotonic() - started_monotonic) * 1000)),
                error_type="WORKER_TRANSIENT_ERROR",
                error_message="simulated retryable worker failure",
                retryable=True,
                payload={
                    "agent_display_name": agent_spec.display_name,
                    "benchmark_display_name": benchmark_spec.display_name,
                    "behavior": behavior,
                },
            )

        finished_at = _utcnow()
        return WorkerResult.success_result(
            worker_id=worker_spec.worker_id,
            trial_id=request.trial.trial_id,
            execution_mode=worker_spec.execution_mode,
            requested_mode=worker_spec.requested_mode,
            attempt=request.attempt,
            worker_pid=os.getpid(),
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=max(1, int((time.monotonic() - started_monotonic) * 1000)),
            payload={
                "agent_display_name": agent_spec.display_name,
                "benchmark_display_name": benchmark_spec.display_name,
                "agent_runtime": request.trial.agent_runtime,
                "benchmark_runtime": request.trial.benchmark_runtime,
                "control_backend": request.trial.control_backend,
                "behavior": behavior,
                "step_count": min(request.trial.max_steps, 1),
            },
        )

    def _require_worker_spec(self) -> WorkerSpec:
        if self._worker_spec is None:
            raise RuntimeError("worker service must be initialized before running a trial")
        return self._worker_spec

    def _resolve_behavior(self, request: WorkerRunRequest) -> str:
        configured = request.trial.env_vars.get("SNOWL_DUMMY_WORKER_BEHAVIOR")
        if configured:
            return configured
        if request.trial.agent_id == "dummy_vision_agent" and request.attempt == 1:
            return "retry_once"
        return "success"
