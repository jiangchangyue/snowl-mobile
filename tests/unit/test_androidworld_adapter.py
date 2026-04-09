from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from snowl_mobile.adapters.benchmarks.androidworld import (
    AndroidWorldBenchmarkAdapter,
    resolve_androidworld_repo_path,
    build_androidworld_contract,
)
from snowl_mobile.adapters.benchmarks import androidworld_runtime as androidworld_runtime_module
from snowl_mobile.adapters.builtin import create_builtin_registry
from snowl_mobile.core.config_loader import load_project_spec
from snowl_mobile.core.errors import IntegrationError
from snowl_mobile.core.planner import ExecutionPlanner
from snowl_mobile.core.run_context import RunContext
from snowl_mobile.core.trial_context import TrialContext


ANDROIDWORLD_CONFIG = ROOT / "configs" / "integrations" / "androidworld" / "minimal.yml"
ANDROIDWORLD_RUN_CONFIG = ROOT / "configs" / "runs" / "androidworld_benchmark.yml"


class AndroidWorldAdapterTestCase(unittest.TestCase):
    def test_builtin_registry_registers_androidworld_adapter(self) -> None:
        registry = create_builtin_registry()

        entry = registry.resolve_benchmark("androidworld")

        self.assertEqual(entry.adapter_id, "androidworld")
        self.assertEqual(entry.metadata.integration_mode, "hybrid")
        self.assertIn("ANDROID_WORLD_HOME", entry.metadata.required_env)
        self.assertEqual(entry.metadata.supported_backends, ("adb",))
        self.assertEqual(
            entry.metadata.extra["supported_suite_families"],
            ["android_world", "android", "miniwob", "miniwob_subset", "information_retrieval"],
        )

    def test_task_discovery_uses_androidworld_registry_and_options(self) -> None:
        adapter = AndroidWorldBenchmarkAdapter()
        spec = load_project_spec(ANDROIDWORLD_CONFIG)
        run_context = RunContext(
            run_id="androidworld-test-run",
            project_snapshot=spec,
            artifact_root=ROOT / "runs" / "androidworld-test-run",
        )

        tasks = adapter.list_tasks(run_context)

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["task_id"], "android:SimpleSmsSend")
        self.assertEqual(tasks[0]["suite_family"], "android")
        self.assertEqual(tasks[0]["task_name"], "SimpleSmsSend")
        self.assertEqual(tasks[0]["n_task_combinations"], 1)
        self.assertIsInstance(tasks[0]["task_instance_seed"], int)

    def test_task_discovery_prefers_materialized_goal_when_worker_python_can_resolve_it(self) -> None:
        adapter = AndroidWorldBenchmarkAdapter()
        spec = load_project_spec(ANDROIDWORLD_CONFIG)
        run_context = RunContext(
            run_id="androidworld-test-run",
            project_snapshot=spec,
            artifact_root=ROOT / "runs" / "androidworld-test-run",
        )

        with mock.patch(
            "snowl_mobile.adapters.benchmarks.androidworld.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=["python", "-c", "helper"],
                returncode=0,
                stdout=json.dumps(
                    {
                        "goal": "Send a text message using Simple SMS Messenger to +16597910719 with message: Beauty is in the eye of the beholder."
                    }
                ),
                stderr="",
            ),
        ) as mocked_run:
            tasks = adapter.list_tasks(run_context)

        self.assertEqual(
            tasks[0]["instruction"],
            "Send a text message using Simple SMS Messenger to +16597910719 with message: Beauty is in the eye of the beholder.",
        )
        self.assertTrue(mocked_run.called)

    def test_information_retrieval_task_discovery_ignores_nested_field_names(self) -> None:
        adapter = AndroidWorldBenchmarkAdapter()

        task_names = adapter._extract_information_retrieval_task_names(  # noqa: SLF001
            resolve_androidworld_repo_path()
        )

        self.assertIn("TasksHighPriorityTasks", task_names)
        self.assertIn("NotesTodoItemCount", task_names)
        self.assertNotIn("time", task_names)
        self.assertNotIn("title", task_names)
        self.assertNotIn("person", task_names)
        self.assertNotIn("start_date", task_names)

    def test_androidworld_contract_is_validated(self) -> None:
        contract = build_androidworld_contract()

        self.assertIn("android_world/registry.py", contract.task_discovery_entry)
        self.assertIn("env_launcher.py::load_and_setup_env", contract.environment_init_entry)
        self.assertEqual(contract.native_metric_mappings[0].platform_metric, "task_success")

    def test_mock_benchmark_probe_writes_artifacts(self) -> None:
        spec = load_project_spec(ANDROIDWORLD_RUN_CONFIG)
        registry = create_builtin_registry()
        planner = ExecutionPlanner(registry=registry)
        plan = planner.plan(spec, run_id="androidworld-benchmark-unit")
        entry = plan.planned_trials[0]
        adapter = AndroidWorldBenchmarkAdapter()

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            request = adapter.build_probe_request(
                TrialContext(
                    trial_spec=entry.trial,
                    emulator_instance_id="androidworld_api33-01",
                    emulator_adb_serial="emulator-5554",
                    trial_output_dir=output_dir,
                ),
                output_dir=output_dir,
                operation="probe",
                task_payload=entry.task.payload,
                task_instruction=entry.task.instruction,
                emulator_instance=None,
                mock_mode=True,
            )

            result = adapter.run_benchmark_probe(request)

            self.assertEqual(result.observation.source_backend, "androidworld")
            self.assertEqual(result.score_bundle.native_metrics["task_success"], 0.0)
            self.assertIn("androidworld_request", result.raw_artifacts)
            self.assertIn("androidworld_result", result.raw_artifacts)
            self.assertTrue((output_dir / result.raw_artifacts["androidworld_request"]).exists())
            self.assertTrue((output_dir / result.raw_artifacts["androidworld_result"]).exists())
            self.assertTrue(result.notes)

    def test_runtime_import_failure_is_preserved_and_surfaced(self) -> None:
        spec = load_project_spec(ANDROIDWORLD_RUN_CONFIG)
        registry = create_builtin_registry()
        planner = ExecutionPlanner(registry=registry)
        plan = planner.plan(spec, run_id="androidworld-benchmark-unit")
        entry = plan.planned_trials[0]
        adapter = AndroidWorldBenchmarkAdapter()

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            request = adapter.build_probe_request(
                TrialContext(
                    trial_spec=entry.trial,
                    emulator_instance_id="androidworld_api33-01",
                    emulator_adb_serial="emulator-5554",
                    trial_output_dir=output_dir,
                ),
                output_dir=output_dir,
                operation="setup",
                task_payload=entry.task.payload,
                task_instruction=entry.task.instruction,
                emulator_instance=None,
                mock_mode=False,
            )

            def _fake_completed_process(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
                failure_path = output_dir / "raw" / "androidworld" / "failure.json"
                failure_path.parent.mkdir(parents=True, exist_ok=True)
                failure_path.write_text(
                    json.dumps(
                        {
                            "error_type": "RuntimeError",
                            "error_message": (
                                "RUNTIME_IMPORT_ERROR: failed to import "
                                "'android_world.registry' from the configured AndroidWorld worker "
                                "interpreter. Missing package appears to be 'absl'. Install the "
                                "upstream dependencies, for example "
                                "`python -m pip install -r references/benchmarks/android_world/requirements.txt`."
                            ),
                        },
                        indent=2,
                        sort_keys=True,
                    ),
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(
                    args=["python", "-m", "snowl_mobile.adapters.benchmarks.androidworld_runtime"],
                    returncode=1,
                    stdout="",
                    stderr="traceback placeholder",
                )

            with mock.patch("snowl_mobile.adapters.benchmarks.androidworld.subprocess.run", side_effect=_fake_completed_process):
                with self.assertRaises(IntegrationError) as raised:
                    adapter.run_benchmark_probe(request)

            message = str(raised.exception)
            self.assertIn("failure.json", message)
            self.assertIn("Missing package appears to be 'absl'", message)
            self.assertIn("ANDROID_WORLD_PYTHON", message)

            merged_failure = json.loads((output_dir / "raw" / "androidworld" / "failure.json").read_text(encoding="utf-8"))
            self.assertEqual(merged_failure["returncode"], 1)
            self.assertIn("error_message", merged_failure)
            self.assertIn("python_executable", merged_failure)

    def test_benchmark_runtime_setup_uses_instance_level_app_names(self) -> None:
        class FakeController:
            def refresh_env(self) -> None:
                return None

        class FakeEnv:
            def __init__(self) -> None:
                self.controller = FakeController()

        class FakeTask:
            def __init__(self) -> None:
                self.app_names = ("joplin",)

        setup_calls = {"count": 0}

        class FakeDeviceSetup:
            @staticmethod
            def get_app_mapping(app_name: str) -> object | None:
                if app_name == "joplin":
                    return object()
                return None

            @staticmethod
            def maybe_install_app(app_class: object, env: object) -> None:
                return None

            @staticmethod
            def setup_app(app_class: object, env: object) -> None:
                setup_calls["count"] += 1

        class FakeAdbUtils:
            @staticmethod
            def press_home_button(controller: object) -> None:
                return None

            @staticmethod
            def set_root_if_needed(controller: object) -> None:
                return None

        fake_env_module = mock.Mock(adb_utils=FakeAdbUtils)
        fake_setup_device_module = mock.Mock(setup=FakeDeviceSetup)

        with mock.patch.object(androidworld_runtime_module, "_require_runtime_import", return_value=None):
            with mock.patch.dict(
                sys.modules,
                {
                    "android_world.env": fake_env_module,
                    "android_world.env.adb_utils": FakeAdbUtils,
                    "android_world.env.setup_device": fake_setup_device_module,
                    "android_world.env.setup_device.setup": FakeDeviceSetup,
                },
                clear=False,
            ):
                installed_apps = androidworld_runtime_module._setup_task_scoped_apps(
                    task_target=FakeTask(),
                    env=FakeEnv(),
                    install_hint="pip install -r requirements.txt",
                )

        self.assertEqual(installed_apps, ("joplin",))
        self.assertEqual(setup_calls["count"], 1)


if __name__ == "__main__":
    unittest.main()
