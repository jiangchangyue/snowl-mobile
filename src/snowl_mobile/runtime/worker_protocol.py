from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from snowl_mobile.core.enums import WorkerMode
from snowl_mobile.core.runtime_recipe import RuntimeRecipe
from snowl_mobile.core.trial_spec import TrialSpec
from snowl_mobile.schemas.base import SchemaModel
from snowl_mobile.schedulers.retry_controller import TrialFailure


WORKER_PROTOCOL_VERSION = "snowl-mobile.worker.v1"


def _utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def map_worker_mode_to_execution_mode(worker_mode: WorkerMode) -> str:
    if worker_mode == WorkerMode.IN_PROCESS:
        return "in_process"
    return "subprocess"


def _build_worker_pythonpath(*, cwd: Path | None, recipe_env_vars: dict[str, str]) -> str | None:
    entries: list[str] = []
    src_dir = (cwd or Path.cwd()).resolve() / "src"
    if src_dir.is_dir():
        entries.append(str(src_dir))

    recipe_pythonpath = recipe_env_vars.get("PYTHONPATH", "").strip()
    if recipe_pythonpath:
        entries.extend(item for item in recipe_pythonpath.split(os.pathsep) if item)

    existing_pythonpath = os.environ.get("PYTHONPATH", "").strip()
    if existing_pythonpath:
        entries.extend(item for item in existing_pythonpath.split(os.pathsep) if item)

    deduped: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        normalized = entry.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    if not deduped:
        return None
    return os.pathsep.join(deduped)


@dataclass(frozen=True, slots=True)
class WorkerTrialInput(SchemaModel):
    trial_id: str
    run_id: str
    agent_id: str
    benchmark_id: str
    model_id: str
    seed: str
    task_id: str
    timeout_sec: int
    max_steps: int
    worker_mode: str
    env_isolation: str
    control_backend: str
    agent_runtime: str
    benchmark_runtime: str
    required_env: tuple[str, ...] = ()
    env_vars: dict[str, str] = field(default_factory=dict)
    backend_requirements: tuple[str, ...] = ()
    mounts: tuple[str, ...] = ()
    bridge_id: str = ""
    pair_recipe_id: str = ""
    ports: dict[str, int] = field(default_factory=dict)
    launch_hints: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_trial_spec(cls, trial_spec: TrialSpec) -> "WorkerTrialInput":
        recipe = trial_spec.runtime_recipe
        return cls(
            trial_id=trial_spec.trial_id,
            run_id=trial_spec.run_id,
            agent_id=trial_spec.agent_id,
            benchmark_id=trial_spec.benchmark_id,
            model_id=trial_spec.model_id,
            seed=trial_spec.seed,
            task_id=trial_spec.task_id,
            timeout_sec=trial_spec.timeout_sec,
            max_steps=trial_spec.max_steps,
            worker_mode=recipe.worker_mode.value,
            env_isolation=recipe.env_isolation.value,
            control_backend=recipe.control_backend,
            agent_runtime=recipe.agent_runtime,
            benchmark_runtime=recipe.benchmark_runtime,
            required_env=recipe.required_env,
            env_vars=recipe.env_vars,
            backend_requirements=recipe.backend_requirements,
            mounts=recipe.mounts,
            bridge_id=recipe.bridge_id,
            pair_recipe_id=recipe.pair_recipe_id,
            ports=recipe.ports,
            launch_hints=recipe.launch_hints,
        )

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "WorkerTrialInput":
        return cls(
            trial_id=str(data["trial_id"]),
            run_id=str(data["run_id"]),
            agent_id=str(data["agent_id"]),
            benchmark_id=str(data["benchmark_id"]),
            model_id=str(data["model_id"]),
            seed=str(data["seed"]),
            task_id=str(data["task_id"]),
            timeout_sec=int(data["timeout_sec"]),
            max_steps=int(data["max_steps"]),
            worker_mode=str(data["worker_mode"]),
            env_isolation=str(data["env_isolation"]),
            control_backend=str(data["control_backend"]),
            agent_runtime=str(data["agent_runtime"]),
            benchmark_runtime=str(data["benchmark_runtime"]),
            required_env=tuple(str(item) for item in data.get("required_env", [])),
            env_vars={str(key): str(value) for key, value in data.get("env_vars", {}).items()},
            backend_requirements=tuple(str(item) for item in data.get("backend_requirements", [])),
            mounts=tuple(str(item) for item in data.get("mounts", [])),
            bridge_id=str(data.get("bridge_id", "")),
            pair_recipe_id=str(data.get("pair_recipe_id", "")),
            ports={str(key): int(value) for key, value in data.get("ports", {}).items()},
            launch_hints={str(key): str(value) for key, value in data.get("launch_hints", {}).items()},
        )


@dataclass(frozen=True, slots=True)
class WorkerRunRequest(SchemaModel):
    trial: WorkerTrialInput
    attempt: int

    @classmethod
    def from_trial_state(cls, trial_spec: TrialSpec, *, attempt: int) -> "WorkerRunRequest":
        return cls(
            trial=WorkerTrialInput.from_trial_spec(trial_spec),
            attempt=attempt,
        )

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "WorkerRunRequest":
        return cls(
            trial=WorkerTrialInput.from_mapping(dict(data["trial"])),
            attempt=int(data["attempt"]),
        )


@dataclass(frozen=True, slots=True)
class WorkerSpec(SchemaModel):
    worker_id: str
    execution_mode: str
    requested_mode: str
    env_isolation: str
    startup_timeout_sec: int
    trial_timeout_sec: int
    cwd: str
    python_executable: str | None = None
    command: tuple[str, ...] = ()
    required_env: tuple[str, ...] = ()
    env_vars: dict[str, str] = field(default_factory=dict)
    backend_requirements: tuple[str, ...] = ()
    mounts: tuple[str, ...] = ()
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_trial_spec(
        cls,
        trial_spec: TrialSpec,
        *,
        startup_timeout_sec: int = 5,
        trial_timeout_sec: int | None = None,
        cwd: Path | None = None,
    ) -> "WorkerSpec":
        recipe = trial_spec.runtime_recipe
        execution_mode = map_worker_mode_to_execution_mode(recipe.worker_mode)
        command: tuple[str, ...] = ()
        python_executable: str | None = None
        env_vars = {
            "SNOWL_WORKER_REQUESTED_MODE": recipe.worker_mode.value,
            "SNOWL_WORKER_PROTOCOL_VERSION": WORKER_PROTOCOL_VERSION,
            **recipe.env_vars,
        }
        if execution_mode == "subprocess":
            python_executable = sys.executable
            command = (python_executable, "-m", "snowl_mobile.runtime.worker_main")
            worker_pythonpath = _build_worker_pythonpath(cwd=cwd, recipe_env_vars=env_vars)
            if worker_pythonpath:
                env_vars["PYTHONPATH"] = worker_pythonpath
        working_dir = str((cwd or Path.cwd()).resolve())
        return cls(
            worker_id=f"{trial_spec.trial_id}-{execution_mode}",
            execution_mode=execution_mode,
            requested_mode=recipe.worker_mode.value,
            env_isolation=recipe.env_isolation.value,
            startup_timeout_sec=startup_timeout_sec,
            trial_timeout_sec=trial_timeout_sec or trial_spec.timeout_sec,
            cwd=working_dir,
            python_executable=python_executable,
            command=command,
            required_env=recipe.required_env,
            env_vars=env_vars,
            backend_requirements=recipe.backend_requirements,
            mounts=recipe.mounts,
            extra={
                "agent_runtime": recipe.agent_runtime,
                "benchmark_runtime": recipe.benchmark_runtime,
                "control_backend": recipe.control_backend,
                "device_profile": recipe.device_profile,
                "reset_policy": recipe.reset_policy,
                "bridge_id": recipe.bridge_id,
                "pair_recipe_id": recipe.pair_recipe_id,
                "ports": recipe.ports,
                "launch_hints": recipe.launch_hints,
            },
        )

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "WorkerSpec":
        return cls(
            worker_id=str(data["worker_id"]),
            execution_mode=str(data["execution_mode"]),
            requested_mode=str(data["requested_mode"]),
            env_isolation=str(data["env_isolation"]),
            startup_timeout_sec=int(data["startup_timeout_sec"]),
            trial_timeout_sec=int(data["trial_timeout_sec"]),
            cwd=str(data["cwd"]),
            python_executable=None
            if data.get("python_executable") is None
            else str(data["python_executable"]),
            command=tuple(str(item) for item in data.get("command", [])),
            required_env=tuple(str(item) for item in data.get("required_env", [])),
            env_vars={str(key): str(value) for key, value in data.get("env_vars", {}).items()},
            backend_requirements=tuple(str(item) for item in data.get("backend_requirements", [])),
            mounts=tuple(str(item) for item in data.get("mounts", [])),
            extra={str(key): value for key, value in data.get("extra", {}).items()},
        )


@dataclass(frozen=True, slots=True)
class WorkerHandshake(SchemaModel):
    worker_id: str
    execution_mode: str
    requested_mode: str
    protocol_version: str
    worker_pid: int | None = None
    started_at: str = field(default_factory=_utcnow)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "WorkerHandshake":
        worker_pid = data.get("worker_pid")
        return cls(
            worker_id=str(data["worker_id"]),
            execution_mode=str(data["execution_mode"]),
            requested_mode=str(data["requested_mode"]),
            protocol_version=str(data["protocol_version"]),
            worker_pid=None if worker_pid is None else int(worker_pid),
            started_at=str(data.get("started_at", _utcnow())),
        )


@dataclass(frozen=True, slots=True)
class WorkerResult(SchemaModel):
    worker_id: str
    trial_id: str
    success: bool
    retryable: bool
    execution_mode: str
    requested_mode: str
    attempt: int
    worker_pid: int | None = None
    started_at: str = field(default_factory=_utcnow)
    finished_at: str = field(default_factory=_utcnow)
    duration_ms: int = 0
    error_type: str | None = None
    error_message: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success_result(
        cls,
        *,
        worker_id: str,
        trial_id: str,
        execution_mode: str,
        requested_mode: str,
        attempt: int,
        worker_pid: int | None,
        started_at: str,
        finished_at: str,
        duration_ms: int,
        payload: dict[str, Any],
    ) -> "WorkerResult":
        return cls(
            worker_id=worker_id,
            trial_id=trial_id,
            success=True,
            retryable=False,
            execution_mode=execution_mode,
            requested_mode=requested_mode,
            attempt=attempt,
            worker_pid=worker_pid,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            payload=payload,
        )

    @classmethod
    def failure_result(
        cls,
        *,
        worker_id: str,
        trial_id: str,
        execution_mode: str,
        requested_mode: str,
        attempt: int,
        error_type: str,
        error_message: str,
        retryable: bool,
        worker_pid: int | None = None,
        started_at: str | None = None,
        finished_at: str | None = None,
        duration_ms: int = 0,
        payload: dict[str, Any] | None = None,
    ) -> "WorkerResult":
        return cls(
            worker_id=worker_id,
            trial_id=trial_id,
            success=False,
            retryable=retryable,
            execution_mode=execution_mode,
            requested_mode=requested_mode,
            attempt=attempt,
            worker_pid=worker_pid,
            started_at=started_at or _utcnow(),
            finished_at=finished_at or _utcnow(),
            duration_ms=duration_ms,
            error_type=error_type,
            error_message=error_message,
            payload=payload or {},
        )

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "WorkerResult":
        worker_pid = data.get("worker_pid")
        return cls(
            worker_id=str(data["worker_id"]),
            trial_id=str(data["trial_id"]),
            success=bool(data["success"]),
            retryable=bool(data["retryable"]),
            execution_mode=str(data["execution_mode"]),
            requested_mode=str(data["requested_mode"]),
            attempt=int(data["attempt"]),
            worker_pid=None if worker_pid is None else int(worker_pid),
            started_at=str(data["started_at"]),
            finished_at=str(data["finished_at"]),
            duration_ms=int(data["duration_ms"]),
            error_type=None if data.get("error_type") is None else str(data["error_type"]),
            error_message=None
            if data.get("error_message") is None
            else str(data["error_message"]),
            payload=dict(data.get("payload", {})),
        )

    def to_trial_failure(self) -> TrialFailure:
        return TrialFailure(
            error_type=self.error_type or "WORKER_FAILURE",
            message=self.error_message or "worker execution failed",
            retryable=self.retryable,
        )
