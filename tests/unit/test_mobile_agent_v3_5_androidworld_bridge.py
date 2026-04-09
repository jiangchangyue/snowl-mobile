from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from snowl_mobile.adapters.bridges.mobile_agent_v3_5_androidworld import (  # noqa: E402
    MobileAgentV35AndroidWorldBridgeAdapter,
)
from snowl_mobile.adapters.bridges import mobile_agent_v3_5_androidworld_runtime as runtime_module  # noqa: E402
from snowl_mobile.adapters.builtin import create_builtin_registry  # noqa: E402
from snowl_mobile.core.config_loader import load_project_spec  # noqa: E402
from snowl_mobile.core.planner import ExecutionPlanner  # noqa: E402
from snowl_mobile.core.trial_context import TrialContext  # noqa: E402
from snowl_mobile.devices.emulator_instance import EmulatorInstance, HealthStatus  # noqa: E402


PAIR_CONFIG = ROOT / "configs" / "runs" / "mobile_agent_v3_5_androidworld.yml"


class MobileAgentV35AndroidWorldBridgeTestCase(unittest.TestCase):
    def _smoke_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["SNOWL_ANDROIDWORLD_SUITE_FAMILY"] = "android"
        env["SNOWL_ANDROIDWORLD_TASKS"] = "SimpleSmsSend"
        return env

    def test_registry_registers_mobile_agent_v3_5_androidworld_bridge(self) -> None:
        registry = create_builtin_registry()

        entry = registry.resolve_bridge_for_pair("mobile_agent_v3_5", "androidworld")

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.adapter_id, "mobile_agent_v3_5__androidworld")
        self.assertTrue(entry.metadata.extra["requires_pair_recipe"])

    def test_plan_selects_bridge_and_pair_recipe(self) -> None:
        with mock.patch.dict(os.environ, self._smoke_env(), clear=False):
            spec = load_project_spec(PAIR_CONFIG)
        planner = ExecutionPlanner(registry=create_builtin_registry())

        plan = planner.plan(spec)

        self.assertEqual(len(plan.planned_trials), 1)
        trial = plan.planned_trials[0].trial
        self.assertEqual(trial.runtime_recipe.bridge_id, "mobile_agent_v3_5__androidworld")
        self.assertEqual(trial.runtime_recipe.pair_recipe_id, "mobile_agent_v3_5_androidworld_existing_device")

    def test_mock_bridge_run_writes_pair_artifacts(self) -> None:
        with mock.patch.dict(os.environ, self._smoke_env(), clear=False):
            spec = load_project_spec(PAIR_CONFIG)
        planner = ExecutionPlanner(registry=create_builtin_registry())
        plan = planner.plan(spec)
        trial = plan.planned_trials[0].trial
        task = plan.planned_trials[0].task
        bridge = MobileAgentV35AndroidWorldBridgeAdapter()
        model = spec.models[0]
        emulator = EmulatorInstance(
            instance_id="fake-androidworld-v35-01",
            adb_serial="emulator-5554",
            appium_port=4723,
            grpc_port=8554,
            avd_name="AndroidWorldAvd",
            snapshot_name="androidworld_base",
            profile_id="androidworld_api33",
        )
        emulator.mark_health(HealthStatus.HEALTHY)
        ctx = TrialContext(trial_spec=trial, emulator_instance_id=emulator.instance_id)

        with tempfile.TemporaryDirectory() as temp_dir:
            request = bridge.build_run_request(
                ctx,
                output_dir=Path(temp_dir),
                emulator_instance=emulator,
                model_spec=model,
                task_payload=task.payload,
                task_instruction=task.instruction,
                mock_mode=True,
            )
            result = bridge.run_wrapped_pair(request)

            self.assertEqual(result.platform_metrics["mock_mode"], True)
            self.assertEqual(len(result.trajectory_steps), 1)
            self.assertIn("bridge_request", result.raw_artifacts)
            self.assertTrue(
                (
                    Path(temp_dir)
                    / "raw"
                    / "mobile_agent_v3_5_androidworld"
                    / "bridge_request.json"
                ).exists()
            )
            self.assertTrue(
                (
                    Path(temp_dir)
                    / "raw"
                    / "mobile_agent_v3_5_androidworld"
                    / "final_result.json"
                ).exists()
            )
            self.assertTrue(
                (
                    Path(temp_dir)
                    / "raw"
                    / "mobile_agent_v3_5"
                    / "wrapped_result.json"
                ).exists()
            )

    def test_runtime_preserves_loaded_env_for_task_scoped_setup(self) -> None:
        class FakePixels:
            shape = (1, 1, 3)

            def tobytes(self) -> bytes:
                return b"\x00\x00\x00"

        class FakeState:
            pixels = FakePixels()
            ui_elements: list[object] = []
            auxiliaries = {}

        class FakeEnv:
            foreground_activity_name = "com.example/.MainActivity"
            logical_screen_size = (1080, 2400)
            orientation = 0
            interaction_cache = ""

            def __init__(self) -> None:
                self.closed = False
                self.reset_calls: list[bool] = []

            def reset(self, *, go_home: bool = True) -> None:
                self.reset_calls.append(go_home)

            def get_state(self, *, wait_to_stabilize: bool = True) -> FakeState:
                return FakeState()

            def close(self) -> None:
                self.closed = True

        class FakeTask:
            complexity = 0.1
            goal = "Send a text message."
            initialized = False
            start_on_home_screen = True

            def __init__(self, params: dict[str, object]) -> None:
                self.params = params

            @staticmethod
            def generate_random_params() -> dict[str, object]:
                return {}

            def initialize_task(self, env: FakeEnv) -> None:
                self.initialized = True

            def is_successful(self, env: FakeEnv) -> float:
                return 1.0

            def tear_down(self, env: FakeEnv) -> None:
                return None

        class FakeTaskRegistry:
            def get_registry(self, suite_family: str) -> dict[str, object]:
                self.last_suite_family = suite_family
                return {"SimpleSmsSend": FakeTask}

        fake_env = FakeEnv()
        setup_envs: list[object] = []

        fake_android_world = ModuleType("android_world")
        fake_registry_module = ModuleType("android_world.registry")
        fake_registry_module.TaskRegistry = FakeTaskRegistry
        fake_env_package = ModuleType("android_world.env")
        fake_env_launcher_module = ModuleType("android_world.env.env_launcher")
        fake_env_launcher_module.load_and_setup_env = lambda **_: fake_env
        fake_env_package.env_launcher = fake_env_launcher_module
        fake_android_world.registry = fake_registry_module

        class FakeAgentAdapter:
            def run_wrapped_agent(self, request: object) -> object:
                return SimpleNamespace(
                    raw_artifacts={},
                    platform_metrics={},
                    trajectory_steps=(),
                    notes=(),
                )

        def fake_setup_task_scoped_apps(
            *,
            task_type: object,
            env: object,
            install_hint: str,
            adb_path: str | None = None,
            adb_serial: str | None = None,
            trial_logger: object | None = None,
        ) -> tuple[str, ...]:
            setup_envs.append(env)
            return ("SimpleSMSMessenger",)

        request = {
            "output_dir": tempfile.mkdtemp(),
            "trial_id": "mobile_agent_v3_5__androidworld-android-simplesmssend-seed-0001",
            "repo_paths": {
                "mobile_agent_v3_5": ROOT.as_posix(),
                "androidworld": ROOT.as_posix(),
            },
            "model": {
                "model_id": "demo-model",
                "provider": "openai_compatible",
            },
            "benchmark_options": {
                "suite_family": "android",
                "perform_emulator_setup": False,
                "console_port": 5554,
                "grpc_port": 8554,
            },
            "task_payload": {
                "task_name": "SimpleSmsSend",
                "suite_family": "android",
                "task_instance_seed": 30,
            },
            "task_instruction": "Send a text message.",
            "device": {
                "adb_serial": "emulator-5554",
                "console_port": 5554,
                "grpc_port": 8554,
            },
            "max_steps": 1,
            "timeout_sec": 1,
        }

        with mock.patch.dict(
            sys.modules,
            {
                "android_world": fake_android_world,
                "android_world.registry": fake_registry_module,
                "android_world.env": fake_env_package,
                "android_world.env.env_launcher": fake_env_launcher_module,
            },
            clear=False,
        ):
            with mock.patch.object(runtime_module, "_require_runtime_import", return_value=None):
                with mock.patch.object(runtime_module, "_setup_task_scoped_apps", side_effect=fake_setup_task_scoped_apps):
                    with mock.patch.object(runtime_module, "_patch_androidworld_clear_directory", return_value=lambda: None):
                        with mock.patch.object(
                            runtime_module,
                            "_patch_androidworld_a11y_forwarder_install",
                            return_value=lambda: None,
                        ):
                            with mock.patch.object(runtime_module, "MobileAgentV35AgentAdapter", FakeAgentAdapter):
                                result = runtime_module._run_pair(request)

        self.assertEqual(setup_envs, [fake_env])
        self.assertEqual(result["platform_metrics"]["setup_apps"], ["SimpleSMSMessenger"])

    def test_bridge_formats_task_scoring_failure_clearly(self) -> None:
        bridge = MobileAgentV35AndroidWorldBridgeAdapter()
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            stderr_path = output_dir / "raw" / "mobile_agent_v3_5_androidworld" / "bridge_stderr.txt"
            stderr_path.parent.mkdir(parents=True, exist_ok=True)
            stderr_path.write_text("no such table: playing_queue", encoding="utf-8")

            message = bridge._format_runtime_failure(
                failure_detail={
                    "error_message": (
                        "ANDROIDWORLD_TASK_ERROR: task scoring failed after execution: no such table: "
                        "playing_queue"
                    )
                },
                stderr_path=stderr_path,
                request=mock.Mock(output_dir=output_dir),
            )

        self.assertIn("native scoring failed after the agent finished", message)
        self.assertIn("raw/mobile_agent_v3_5_androidworld/failure.json", message)

    def test_bridge_formats_bootstrap_ui_failure_clearly(self) -> None:
        bridge = MobileAgentV35AndroidWorldBridgeAdapter()
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            stderr_path = output_dir / "raw" / "mobile_agent_v3_5_androidworld" / "bridge_stderr.txt"
            stderr_path.parent.mkdir(parents=True, exist_ok=True)
            stderr_path.write_text('Target text "SAVE" not found.', encoding="utf-8")

            message = bridge._format_runtime_failure(
                failure_detail={
                    "error_message": (
                        'MOBILE_AGENT_V3_5_BRIDGE_ERROR: unexpected bridge runtime failure: '
                        'Target text "SAVE" not found.'
                    )
                },
                stderr_path=stderr_path,
                request=mock.Mock(output_dir=output_dir),
            )

        self.assertIn("task bootstrap failed while the benchmark was preparing first-run app state", message)
        self.assertIn("retries bootstrap once", message)

    def test_bridge_formats_missing_db_path_bootstrap_failure_clearly(self) -> None:
        bridge = MobileAgentV35AndroidWorldBridgeAdapter()
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            stderr_path = output_dir / "raw" / "mobile_agent_v3_5_androidworld" / "bridge_stderr.txt"
            stderr_path.parent.mkdir(parents=True, exist_ok=True)
            stderr_path.write_text("/data/data/org.videolan.vlc/app_db does not exist.", encoding="utf-8")

            message = bridge._format_runtime_failure(
                failure_detail={
                    "error_message": (
                        "MOBILE_AGENT_V3_5_BRIDGE_ERROR: unexpected bridge runtime failure: "
                        "/data/data/org.videolan.vlc/app_db does not exist."
                    )
                },
                stderr_path=stderr_path,
                request=mock.Mock(output_dir=output_dir),
            )

        self.assertIn("app-owned SQLite/database initialization problem", message)
        self.assertIn("empty state instead of crashing the trial", message)


if __name__ == "__main__":
    unittest.main()
