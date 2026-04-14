from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from snowl_mobile.adapters.builtin import create_builtin_registry
from snowl_mobile.artifacts.store import ArtifactStore
from snowl_mobile.core.config_loader import load_project_spec
from snowl_mobile.core.logging import configure_logging
from snowl_mobile.core.planner import ExecutionPlanner
from snowl_mobile.core.states import RunStatus, TrialStatus
from snowl_mobile.runtime.trial_orchestrator import TrialOrchestrator
from snowl_mobile.runtime.worker_launcher import WorkerLaunchOutcome, WorkerLauncher
from snowl_mobile.runtime.worker_protocol import WorkerResult
from snowl_mobile.schedulers.retry_controller import RetryController


PROJECT = ROOT / "project.example.yml"


class RuntimeFailureClassificationTestCase(unittest.TestCase):
    def test_missing_runtime_env_is_classified_as_prerequisite_error(self) -> None:
        orchestrator = TrialOrchestrator()
        error_type, message = orchestrator._classify_runtime_failure(  # noqa: SLF001
            RuntimeError(
                "real Open-AutoGLM x MobileSafetyBench runs require these environment variables: "
                "PHONE_AGENT_BASE_URL, PHONE_AGENT_API_KEY"
            )
        )

        self.assertEqual(error_type, "RUNTIME_PREREQUISITE_MISSING")
        self.assertIn("PHONE_AGENT_BASE_URL", message)

    def test_import_preflight_failure_is_classified_as_prerequisite_error(self) -> None:
        orchestrator = TrialOrchestrator()
        error_type, message = orchestrator._classify_runtime_failure(  # noqa: SLF001
            RuntimeError(
                "upstream runtime import preflight failed. Missing Python packages appear to include: "
                "openai, portpicker. Details: Open-AutoGLM:phone_agent.model.client -> "
                "ModuleNotFoundError: No module named 'openai'."
            )
        )

        self.assertEqual(error_type, "RUNTIME_PREREQUISITE_MISSING")
        self.assertIn("openai", message)

    def test_mobile_agent_e_missing_python_packages_is_classified_as_prerequisite_error(self) -> None:
        orchestrator = TrialOrchestrator()
        error_type, message = orchestrator._classify_runtime_failure(  # noqa: SLF001
            RuntimeError(
                "Mobile-Agent-E wrapped execution requires these Python packages in the current environment: "
                "PIL, numpy, cv2, torch, modelscope, dashscope."
            )
        )

        self.assertEqual(error_type, "RUNTIME_PREREQUISITE_MISSING")
        self.assertIn("modelscope", message)

    def test_mobile_agent_e_missing_adb_device_is_classified_as_device_not_found(self) -> None:
        orchestrator = TrialOrchestrator()
        error_type, message = orchestrator._classify_runtime_failure(  # noqa: SLF001
            RuntimeError(
                "No adb device detected for serial 'emulator-5554'. Currently attached devices: <none>. "
                "Start the emulator first and confirm it appears in `adb devices`."
            )
        )

        self.assertEqual(error_type, "DEVICE_NOT_FOUND")
        self.assertIn("emulator-5554", message)

    def test_mobile_agent_e_no_model_response_is_classified_as_model_call_failure(self) -> None:
        orchestrator = TrialOrchestrator()
        error_type, message = orchestrator._classify_runtime_failure(  # noqa: SLF001
            RuntimeError(
                "Model error: Mobile-Agent-E reasoning request returned no response. "
                "api_url=https://example.invalid/v1/chat/completions model=Qwen2.5-VL-72B-Instruct."
            )
        )

        self.assertEqual(error_type, "MODEL_CALL_FAILED")
        self.assertIn("returned no response", message)

    def test_mobile_agent_e_wrapped_subprocess_failure_is_not_misclassified_as_benchmark_error(self) -> None:
        orchestrator = TrialOrchestrator()
        error_type, message = orchestrator._classify_runtime_failure(  # noqa: SLF001
            RuntimeError(
                "Mobile-Agent-E wrapped subprocess failed (exit_code=1). "
                "Inspect /tmp/snowl-mobile-mobile-agent-e-mobilesafetybench-rerun/trials/"
                "mobile_agent_e__mobilesafetybench-text_message_sending-low_risk_001-seed-0001/"
                "raw/mobile_agent_e/failure.json for the captured traceback."
            )
        )

        self.assertEqual(error_type, "AGENT_WORKER_CRASH")
        self.assertIn("wrapped subprocess failed", message)

    def test_androidworld_a11y_runtime_failure_is_classified_as_benchmark_error(self) -> None:
        orchestrator = TrialOrchestrator()
        error_type, message = orchestrator._classify_runtime_failure(  # noqa: SLF001
            RuntimeError(
                "AndroidWorld accessibility runtime became unavailable during task-scoped app setup or task bootstrap. "
                "The emulator may be unhealthy; restart the AVD and then resume with the same output directory."
            )
        )

        self.assertEqual(error_type, "BENCHMARK_RUN_FAILED")
        self.assertIn("accessibility runtime", message)

    def test_androidworld_a11y_runtime_failure_aborts_run_immediately(self) -> None:
        orchestrator = TrialOrchestrator()
        self.assertTrue(
            orchestrator._should_abort_run_immediately(  # noqa: SLF001
                "BENCHMARK_RUN_FAILED",
                "AndroidWorld accessibility runtime became unavailable during task-scoped app setup.",
            )
        )

    def test_model_endpoint_message_is_classified_as_model_call_failure(self) -> None:
        orchestrator = TrialOrchestrator()
        error_type, message = orchestrator._classify_runtime_failure(  # noqa: SLF001
            RuntimeError(
                "Mobile-Agent-E x AndroidWorld could not reach the configured model endpoint. "
                "Check MOBILE_AGENT_E_API_KEY/MOBILE_AGENT_E_BASE_URL and proxy settings."
            )
        )

        self.assertEqual(error_type, "MODEL_CALL_FAILED")
        self.assertIn("configured model endpoint", message)

    def test_mobile_safety_bench_task_invocation_failure_is_classified_as_benchmark_error(self) -> None:
        orchestrator = TrialOrchestrator()
        error_type, message = orchestrator._classify_runtime_failure(  # noqa: SLF001
            RuntimeError("MobileSafetyBench task invocation failed: evaluator bootstrap crashed")
        )

        self.assertEqual(error_type, "BENCHMARK_RUN_FAILED")
        self.assertIn("MobileSafetyBench task invocation failed", message)

    def test_mobilesafetybench_bootstrap_timeout_is_classified_as_adb_backend_error(self) -> None:
        orchestrator = TrialOrchestrator()
        error_type, message = orchestrator._classify_runtime_failure(  # noqa: SLF001
            RuntimeError(
                "Mobile-Agent-v3.5 x MobileSafetyBench pair bridge failed. Original error: IntegrationError: "
                "Timed out waiting for the leased emulator to become ready for benchmark bootstrap. "
                "Last probe failure: adb -s emulator-5558 shell getprop sys.boot_completed failed with code 124: "
                "command timed out after 15 seconds."
            )
        )

        self.assertEqual(error_type, "ADB_BACKEND_ERROR")
        self.assertIn("benchmark bootstrap", message)

    def test_mobilesafetybench_bootstrap_timeout_aborts_run_immediately(self) -> None:
        orchestrator = TrialOrchestrator()
        self.assertTrue(
            orchestrator._should_abort_run_immediately(  # noqa: SLF001
                "ADB_BACKEND_ERROR",
                "Timed out waiting for the leased emulator to become ready for benchmark bootstrap. "
                "Last probe failure: adb -s emulator-5560 wait-for-device failed with code 124: "
                "command timed out after 15 seconds.",
            )
        )

    def test_pair_bridge_runner_timeout_is_classified_as_agent_worker_crash(self) -> None:
        orchestrator = TrialOrchestrator()
        error_type, message = orchestrator._classify_runtime_failure(  # noqa: SLF001
            RuntimeError(
                "Mobile-Agent-v3.5 runtime invocation failed inside the pair bridge. Original error: "
                "TimeoutExpired: Command ['python3', '-m', "
                "'snowl_mobile.adapters.agents.mobile_agent_v3_5_runner'] timed out after 2400 seconds"
            )
        )

        self.assertEqual(error_type, "AGENT_WORKER_CRASH")
        self.assertIn("TimeoutExpired", message)

    def test_pair_bridge_runner_timeout_aborts_run_immediately(self) -> None:
        orchestrator = TrialOrchestrator()
        self.assertTrue(
            orchestrator._should_abort_run_immediately(  # noqa: SLF001
                "AGENT_WORKER_CRASH",
                "Mobile-Agent-v3.5 runtime invocation failed inside the pair bridge. Original error: "
                "TimeoutExpired: Command ['python3', '-m', "
                "'snowl_mobile.adapters.agents.mobile_agent_v3_5_runner'] timed out after 2400 seconds",
            )
        )

    def test_run_aborts_remaining_trials_after_immediate_systemic_failure(self) -> None:
        spec = load_project_spec(PROJECT)
        planner = ExecutionPlanner(registry=create_builtin_registry())
        plan = planner.plan(spec, run_id="abort-systemic-failure")
        configure_logging(verbosity=0)

        class DeviceGoneWorkerLauncher(WorkerLauncher):
            def execute_trial(self, trial_state, **kwargs):  # type: ignore[override]
                worker_spec = self.build_worker_spec(trial_state)
                return WorkerLaunchOutcome(
                    worker_spec=worker_spec,
                    result=WorkerResult.failure_result(
                        worker_id=worker_spec.worker_id,
                        trial_id=trial_state.trial_id,
                        execution_mode=worker_spec.execution_mode,
                        requested_mode=worker_spec.requested_mode,
                        attempt=trial_state.attempt_count,
                        error_type="DEVICE_NOT_FOUND",
                        error_message="adb serial emulator-5554 disappeared during execution",
                        retryable=True,
                    ),
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore()
            layout = store.initialize_run_directory(
                spec=spec,
                project_source=PROJECT,
                run_dir=Path(temp_dir) / "abort-systemic-failure",
                run_id="abort-systemic-failure",
                plan_payload=plan.to_summary(),
                summary_payload={"run_id": "abort-systemic-failure", "status": "RUNNING"},
            )
            orchestrator = TrialOrchestrator(worker_launcher=DeviceGoneWorkerLauncher())
            result = orchestrator.run_platform_pipeline(
                plan,
                spec=spec,
                registry=create_builtin_registry(),
                retry_controller=RetryController(spec.retries),
                run_layout=layout,
                device_count=1,
            )

        self.assertEqual(result.plan.run_context.status, RunStatus.ABORTED)
        statuses = {trial_state.trial_id: trial_state.status for trial_state in result.trial_states}
        self.assertEqual(
            sum(status == TrialStatus.ABORTED for status in statuses.values()),
            len(statuses) - 1,
        )
        self.assertEqual(
            sum(status == TrialStatus.FAILED for status in statuses.values()),
            1,
        )

    def test_task_level_backend_failure_retries_three_times_then_continues(self) -> None:
        spec = load_project_spec(PROJECT)
        planner = ExecutionPlanner(registry=create_builtin_registry())
        plan = planner.plan(spec, run_id="continue-after-task-failure")
        configure_logging(verbosity=0)
        target_trial_id = plan.planned_trials[0].trial.trial_id

        class ActionFailureWorkerLauncher(WorkerLauncher):
            def __init__(self) -> None:
                super().__init__()
                self.attempts: dict[str, int] = {}

            def execute_trial(self, trial_state, **kwargs):  # type: ignore[override]
                worker_spec = self.build_worker_spec(trial_state)
                self.attempts[trial_state.trial_id] = self.attempts.get(trial_state.trial_id, 0) + 1
                if trial_state.trial_id == target_trial_id:
                    return WorkerLaunchOutcome(
                        worker_spec=worker_spec,
                        result=WorkerResult.failure_result(
                            worker_id=worker_spec.worker_id,
                            trial_id=trial_state.trial_id,
                            execution_mode=worker_spec.execution_mode,
                            requested_mode=worker_spec.requested_mode,
                            attempt=trial_state.attempt_count,
                            error_type="ADB_BACKEND_ERROR",
                            error_message=(
                                "Text input did not appear in the focused UI field after trying "
                                "Appium send_keys and adb shell input text."
                            ),
                            retryable=True,
                        ),
                    )
                return WorkerLaunchOutcome(
                    worker_spec=worker_spec,
                    result=WorkerResult.success_result(
                        worker_id=worker_spec.worker_id,
                        trial_id=trial_state.trial_id,
                        execution_mode=worker_spec.execution_mode,
                        requested_mode=worker_spec.requested_mode,
                        attempt=trial_state.attempt_count,
                        worker_pid=None,
                        started_at="2026-03-22T00:00:00+00:00",
                        finished_at="2026-03-22T00:00:01+00:00",
                        duration_ms=1000,
                        payload={},
                    ),
                )

        launcher = ActionFailureWorkerLauncher()
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore()
            layout = store.initialize_run_directory(
                spec=spec,
                project_source=PROJECT,
                run_dir=Path(temp_dir) / "continue-after-task-failure",
                run_id="continue-after-task-failure",
                plan_payload=plan.to_summary(),
                summary_payload={"run_id": "continue-after-task-failure", "status": "RUNNING"},
            )
            orchestrator = TrialOrchestrator(worker_launcher=launcher)
            result = orchestrator.run_platform_pipeline(
                plan,
                spec=spec,
                registry=create_builtin_registry(),
                retry_controller=RetryController(spec.retries),
                run_layout=layout,
                device_count=1,
            )

        self.assertEqual(result.plan.run_context.status, RunStatus.PARTIALLY_FAILED)
        statuses = {trial_state.trial_id: trial_state.status for trial_state in result.trial_states}
        self.assertEqual(statuses[target_trial_id], TrialStatus.FAILED)
        self.assertEqual(result.trial_states[0].attempt_count, 4)
        self.assertEqual(launcher.attempts[target_trial_id], 4)
        self.assertGreaterEqual(
            sum(status == TrialStatus.COMPLETED for status in statuses.values()),
            1,
        )
        self.assertNotIn(TrialStatus.ABORTED, statuses.values())

    def test_run_aborts_on_model_call_failure(self) -> None:
        spec = load_project_spec(PROJECT)
        planner = ExecutionPlanner(registry=create_builtin_registry())
        plan = planner.plan(spec, run_id="abort-model-call-failure")
        configure_logging(verbosity=0)

        class ModelFailureWorkerLauncher(WorkerLauncher):
            def execute_trial(self, trial_state, **kwargs):  # type: ignore[override]
                worker_spec = self.build_worker_spec(trial_state)
                return WorkerLaunchOutcome(
                    worker_spec=worker_spec,
                    result=WorkerResult.failure_result(
                        worker_id=worker_spec.worker_id,
                        trial_id=trial_state.trial_id,
                        execution_mode=worker_spec.execution_mode,
                        requested_mode=worker_spec.requested_mode,
                        attempt=trial_state.attempt_count,
                        error_type="AGENT_WORKER_CRASH",
                        error_message=(
                            "Model error: Connection timed out while calling chat.completions "
                            "on the configured provider."
                        ),
                        retryable=True,
                    ),
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore()
            layout = store.initialize_run_directory(
                spec=spec,
                project_source=PROJECT,
                run_dir=Path(temp_dir) / "abort-model-call-failure",
                run_id="abort-model-call-failure",
                plan_payload=plan.to_summary(),
                summary_payload={"run_id": "abort-model-call-failure", "status": "RUNNING"},
            )
            orchestrator = TrialOrchestrator(worker_launcher=ModelFailureWorkerLauncher())
            result = orchestrator.run_platform_pipeline(
                plan,
                spec=spec,
                registry=create_builtin_registry(),
                retry_controller=RetryController(spec.retries),
                run_layout=layout,
                device_count=1,
            )

        self.assertEqual(result.plan.run_context.status, RunStatus.ABORTED)
        statuses = {trial_state.trial_id: trial_state.status for trial_state in result.trial_states}
        self.assertEqual(
            sum(status == TrialStatus.ABORTED for status in statuses.values()),
            len(statuses) - 1,
        )
        self.assertEqual(
            sum(status == TrialStatus.FAILED for status in statuses.values()),
            1,
        )


if __name__ == "__main__":
    unittest.main()
