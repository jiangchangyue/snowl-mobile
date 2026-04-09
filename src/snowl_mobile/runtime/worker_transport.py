from __future__ import annotations

import json
import os
import selectors
import subprocess
from pathlib import Path
from typing import Protocol

from snowl_mobile.core.errors import WorkerCrashError, WorkerProtocolError, WorkerTimeoutError
from snowl_mobile.runtime.worker_protocol import WorkerHandshake, WorkerResult, WorkerRunRequest, WorkerSpec
from snowl_mobile.runtime.worker_service import DummyWorkerService


class WorkerTransport(Protocol):
    def initialize(self, worker_spec: WorkerSpec) -> WorkerHandshake:
        ...

    def run_trial(self, request: WorkerRunRequest) -> WorkerResult:
        ...

    def close(self) -> None:
        ...


class InProcessWorkerTransport:
    def __init__(self) -> None:
        self._service = DummyWorkerService()
        self._worker_spec: WorkerSpec | None = None

    def initialize(self, worker_spec: WorkerSpec) -> WorkerHandshake:
        self._worker_spec = worker_spec
        return self._service.initialize(worker_spec)

    def run_trial(self, request: WorkerRunRequest) -> WorkerResult:
        if self._worker_spec is None:
            raise WorkerProtocolError("in-process worker was not initialized")
        try:
            return self._service.run_trial(request)
        except Exception as error:  # pragma: no cover - defensive conversion
            raise WorkerCrashError(str(error)) from error

    def close(self) -> None:
        self._worker_spec = None


class SubprocessWorkerTransport:
    def __init__(self) -> None:
        self._process: subprocess.Popen[str] | None = None
        self._worker_spec: WorkerSpec | None = None

    def initialize(self, worker_spec: WorkerSpec) -> WorkerHandshake:
        if not worker_spec.command:
            raise WorkerProtocolError("subprocess worker_spec is missing a command")
        env = os.environ.copy()
        env.update(worker_spec.env_vars)
        try:
            self._process = subprocess.Popen(
                list(worker_spec.command),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=worker_spec.cwd,
                env=env,
            )
        except OSError as error:
            raise WorkerCrashError(f"failed to start worker process: {error}") from error
        self._worker_spec = worker_spec
        self._send_message({"type": "initialize", "worker_spec": worker_spec.to_dict()})
        response = self._read_message(worker_spec.startup_timeout_sec)
        if response.get("type") != "initialized":
            raise WorkerProtocolError(
                f"expected initialized response, received '{response.get('type')}'"
            )
        return WorkerHandshake.from_mapping(dict(response["handshake"]))

    def run_trial(self, request: WorkerRunRequest) -> WorkerResult:
        worker_spec = self._require_worker_spec()
        self._send_message({"type": "run_trial", "request": request.to_dict()})
        response = self._read_message(worker_spec.trial_timeout_sec)
        if response.get("type") != "trial_result":
            raise WorkerProtocolError(
                f"expected trial_result response, received '{response.get('type')}'"
            )
        return WorkerResult.from_mapping(dict(response["result"]))

    def close(self) -> None:
        process = self._process
        self._process = None
        self._worker_spec = None
        if process is None:
            return
        try:
            if process.poll() is None and process.stdin is not None:
                process.stdin.write(json.dumps({"type": "shutdown"}) + "\n")
                process.stdin.flush()
        except OSError:
            pass
        finally:
            if process.poll() is None:
                try:
                    process.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1)
            for handle in (process.stdin, process.stdout, process.stderr):
                if handle is not None:
                    handle.close()

    def _require_process(self) -> subprocess.Popen[str]:
        if self._process is None:
            raise WorkerProtocolError("subprocess worker is not running")
        return self._process

    def _require_worker_spec(self) -> WorkerSpec:
        if self._worker_spec is None:
            raise WorkerProtocolError("subprocess worker was not initialized")
        return self._worker_spec

    def _send_message(self, payload: dict[str, object]) -> None:
        process = self._require_process()
        if process.stdin is None:
            raise WorkerProtocolError("worker stdin is unavailable")
        if process.poll() is not None:
            raise WorkerCrashError(
                f"worker exited before request could be sent (exit_code={process.returncode})"
            )
        try:
            process.stdin.write(json.dumps(payload) + "\n")
            process.stdin.flush()
        except OSError as error:
            raise WorkerCrashError(f"failed to send request to worker: {error}") from error

    def _read_message(self, timeout_sec: int) -> dict[str, object]:
        process = self._require_process()
        if process.stdout is None:
            raise WorkerProtocolError("worker stdout is unavailable")
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        try:
            events = selector.select(timeout_sec)
        finally:
            selector.close()
        if not events:
            self._terminate_process(process)
            raise WorkerTimeoutError(f"worker response timed out after {timeout_sec}s")

        line = process.stdout.readline()
        if not line:
            stderr_output = self._read_stderr(process)
            raise WorkerCrashError(
                "worker exited without sending a response"
                f" (exit_code={process.poll()}, stderr={stderr_output!r})"
            )
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as error:
            stderr_output = self._read_stderr(process)
            raise WorkerProtocolError(
                f"worker returned malformed JSON: {line.strip()!r}; stderr={stderr_output!r}"
            ) from error
        if not isinstance(payload, dict):
            raise WorkerProtocolError("worker response must be a JSON object")
        return payload

    def _terminate_process(self, process: subprocess.Popen[str]) -> None:
        if process.poll() is None:
            process.kill()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass

    def _read_stderr(self, process: subprocess.Popen[str]) -> str:
        if process.stderr is None:
            return ""
        if process.poll() is None:
            selector = selectors.DefaultSelector()
            selector.register(process.stderr, selectors.EVENT_READ)
            try:
                events = selector.select(0)
            finally:
                selector.close()
            if not events:
                return ""
            line = process.stderr.readline()
            return line.strip()
        try:
            return process.stderr.read().strip()
        except OSError:
            return ""
