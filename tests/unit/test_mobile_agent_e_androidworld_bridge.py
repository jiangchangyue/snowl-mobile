from __future__ import annotations

import json
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

from snowl_mobile.adapters.bridges.mobile_agent_e_androidworld import (  # noqa: E402
    MobileAgentEAndroidWorldBridgeAdapter,
    MobileAgentEAndroidWorldRunRequest,
)
from snowl_mobile.adapters.agents import mobile_agent_e_runner as runner_module  # noqa: E402
from snowl_mobile.adapters.bridges import mobile_agent_e_androidworld_runtime as runtime_module  # noqa: E402
from snowl_mobile.adapters.builtin import create_builtin_registry  # noqa: E402
from snowl_mobile.core.config_loader import load_project_spec  # noqa: E402
from snowl_mobile.core.planner import ExecutionPlanner  # noqa: E402
from snowl_mobile.core.trial_context import TrialContext  # noqa: E402
from snowl_mobile.devices.emulator_instance import EmulatorInstance, HealthStatus  # noqa: E402


PAIR_CONFIG = ROOT / "configs" / "runs" / "mobile_agent_e_androidworld.yml"


class MobileAgentEAndroidWorldBridgeTestCase(unittest.TestCase):
    def _smoke_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["SNOWL_ANDROIDWORLD_SUITE_FAMILY"] = "android"
        env["SNOWL_ANDROIDWORLD_TASKS"] = "SimpleSmsSend"
        return env

    def test_runtime_detects_lightweight_perception_flag(self) -> None:
        with mock.patch.dict(os.environ, {"MOBILE_AGENT_E_LIGHTWEIGHT_PERCEPTION": "1"}, clear=False):
            self.assertTrue(runtime_module._mobile_agent_e_lightweight_perception_enabled())

        with mock.patch.dict(os.environ, {"MOBILE_AGENT_E_LIGHTWEIGHT_PERCEPTION": "0"}, clear=False):
            self.assertFalse(runtime_module._mobile_agent_e_lightweight_perception_enabled())

    def test_runner_patches_operator_prompt_single_history_tap_bug(self) -> None:
        fake_agents_module = ModuleType("MobileAgentE.agents")

        class FakeOperator:
            def get_prompt(self, info_pool: object) -> str:
                prompt = ""
                if info_pool.action_history != []:
                    latest_actions = info_pool.action_history[-1:]
                    latest_summary = info_pool.summary_history[-1:]
                    latest_outcomes = info_pool.action_outcomes[-1:]
                    error_descriptions = info_pool.error_descriptions[-1:]
                    action_log_strs = []
                    for act, summ, outcome, err_des in zip(
                        latest_actions,
                        latest_summary,
                        latest_outcomes,
                        error_descriptions,
                    ):
                        if outcome == "A":
                            action_log_str = f"Action: {act} | Description: {summ} | Outcome: Successful\n"
                        else:
                            action_log_str = (
                                f"Action: {act} | Description: {summ} | Outcome: Failed | "
                                f"Feedback: {err_des}\n"
                            )
                        prompt += action_log_str
                        action_log_strs.append(action_log_str)
                    if latest_outcomes[-1] == "C" and "Tap" in action_log_strs[-1] and "Tap" in action_log_strs[-2]:
                        prompt += "hint"
                return prompt

        fake_agents_module.Operator = FakeOperator
        info_pool = SimpleNamespace(
            action_history=["{'name': 'Tap', 'arguments': {'x': 10, 'y': 20}}"],
            summary_history=["Tap the stopwatch widget."],
            action_outcomes=["C"],
            error_descriptions=["The screen did not change."],
        )

        with mock.patch.dict(sys.modules, {"MobileAgentE.agents": fake_agents_module}, clear=False):
            runner_module._patch_operator_prompt_history_guard()
            prompt = fake_agents_module.Operator().get_prompt(info_pool)

        self.assertIn("Action:", prompt)
        self.assertNotIn("hint", prompt)

    def test_registry_registers_mobile_agent_e_androidworld_bridge(self) -> None:
        registry = create_builtin_registry()

        entry = registry.resolve_bridge_for_pair("mobile_agent_e", "androidworld")

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.adapter_id, "mobile_agent_e__androidworld")
        self.assertTrue(entry.metadata.extra["requires_pair_recipe"])

    def test_plan_selects_bridge_and_pair_recipe(self) -> None:
        with mock.patch.dict(os.environ, self._smoke_env(), clear=False):
            spec = load_project_spec(PAIR_CONFIG)
        planner = ExecutionPlanner(registry=create_builtin_registry())

        plan = planner.plan(spec)

        self.assertEqual(len(plan.planned_trials), 1)
        trial = plan.planned_trials[0].trial
        self.assertEqual(trial.runtime_recipe.bridge_id, "mobile_agent_e__androidworld")
        self.assertEqual(trial.runtime_recipe.pair_recipe_id, "mobile_agent_e_androidworld_existing_device")

    def test_mock_bridge_run_writes_pair_artifacts(self) -> None:
        with mock.patch.dict(os.environ, self._smoke_env(), clear=False):
            spec = load_project_spec(PAIR_CONFIG)
        planner = ExecutionPlanner(registry=create_builtin_registry())
        plan = planner.plan(spec)
        trial = plan.planned_trials[0].trial
        task = plan.planned_trials[0].task
        bridge = MobileAgentEAndroidWorldBridgeAdapter()
        model = spec.models[0]
        emulator = EmulatorInstance(
            instance_id="fake-androidworld-01",
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
                    / "mobile_agent_e_androidworld"
                    / "bridge_request.json"
                ).exists()
            )
            self.assertTrue(
                (
                    Path(temp_dir)
                    / "raw"
                    / "mobile_agent_e_androidworld"
                    / "final_result.json"
                ).exists()
            )
            self.assertTrue(
                (
                    Path(temp_dir)
                    / "raw"
                    / "mobile_agent_e"
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
            "trial_id": "mobile_agent_e__androidworld-android-simplesmssend-seed-0001",
            "repo_paths": {
                "mobile_agent_e": ROOT.as_posix(),
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
                            with mock.patch.object(runtime_module, "MobileAgentEAgentAdapter", FakeAgentAdapter):
                                result = runtime_module._run_pair(request)

        self.assertEqual(setup_envs, [fake_env])
        self.assertEqual(result["platform_metrics"]["setup_apps"], ["SimpleSMSMessenger"])

    def test_runtime_promotes_mobile_agent_e_model_api_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trial_dir = Path(temp_dir)
            failure_dir = trial_dir / "raw" / "mobile_agent_e"
            failure_dir.mkdir(parents=True, exist_ok=True)
            (failure_dir / "failure.json").write_text(
                json.dumps(
                    {
                        "error_message": "openai.APIConnectionError: Connection error.",
                        "traceback": "httpx.ConnectError: [SSL: UNEXPECTED_EOF_WHILE_READING]",
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "MODEL_API_ERROR"):
                runtime_module._raise_mobile_agent_e_bridge_error(
                    error=runtime_module.IntegrationError("Mobile-Agent-E wrapped subprocess failed"),
                    trial_dir=trial_dir,
                )

    def test_bridge_formats_androidworld_a11y_failure_clearly(self) -> None:
        bridge = MobileAgentEAndroidWorldBridgeAdapter()
        with tempfile.TemporaryDirectory() as temp_dir:
            spec = load_project_spec(PAIR_CONFIG)
            model = spec.models[0]
            request = MobileAgentEAndroidWorldRunRequest(
                trial_context=mock.Mock(),  # type: ignore[arg-type]
                output_dir=Path(temp_dir),
                emulator_instance=EmulatorInstance(
                    instance_id="emulator-5554",
                    adb_serial="emulator-5554",
                    appium_port=4723,
                    grpc_port=8554,
                    avd_name="AndroidWorldAvd",
                    snapshot_name="default",
                ),
                model_spec=model,
                task_payload={"task_name": "BrowserDraw"},
                task_instruction="Draw in Chrome.",
                mock_mode=False,
            )
            stderr_path = request.output_dir / "raw" / "mobile_agent_e_androidworld" / "bridge_stderr.txt"
            stderr_path.parent.mkdir(parents=True, exist_ok=True)
            stderr_path.write_text("Could not get a11y tree.", encoding="utf-8")

            message = bridge._format_runtime_failure(
                failure_detail={
                    "error_message": "ANDROIDWORLD_ENV_ERROR: AndroidWorld accessibility tree became unavailable during task-scoped app setup for 'chrome'. Original error: Could not get a11y tree."
                },
                stderr_path=stderr_path,
                request=request,
            )

        self.assertIn("accessibility runtime became unavailable", message)
        self.assertIn("resume with the same output directory", message)

    def test_bridge_formats_raw_a11y_tree_failure_clearly(self) -> None:
        bridge = MobileAgentEAndroidWorldBridgeAdapter()
        with tempfile.TemporaryDirectory() as temp_dir:
            spec = load_project_spec(PAIR_CONFIG)
            model = spec.models[0]
            request = MobileAgentEAndroidWorldRunRequest(
                trial_context=mock.Mock(),  # type: ignore[arg-type]
                output_dir=Path(temp_dir),
                emulator_instance=EmulatorInstance(
                    instance_id="emulator-5554",
                    adb_serial="emulator-5554",
                    appium_port=4723,
                    grpc_port=8554,
                    avd_name="AndroidWorldAvd",
                    snapshot_name="default",
                ),
                model_spec=model,
                task_payload={"task_name": "AudioRecorderRecordAudioWithFileName"},
                task_instruction="Record audio.",
                mock_mode=False,
            )
            stderr_path = request.output_dir / "raw" / "mobile_agent_e_androidworld" / "bridge_stderr.txt"
            stderr_path.parent.mkdir(parents=True, exist_ok=True)
            stderr_path.write_text("Could not get a11y tree.", encoding="utf-8")

            message = bridge._format_runtime_failure(
                failure_detail={"error_message": "Could not get a11y tree."},
                stderr_path=stderr_path,
                request=request,
            )

        self.assertIn("accessibility runtime became unavailable", message)

    def test_bridge_formats_invalid_action_json_failure_clearly(self) -> None:
        bridge = MobileAgentEAndroidWorldBridgeAdapter()
        with tempfile.TemporaryDirectory() as temp_dir:
            spec = load_project_spec(PAIR_CONFIG)
            model = spec.models[0]
            request = MobileAgentEAndroidWorldRunRequest(
                trial_context=mock.Mock(),  # type: ignore[arg-type]
                output_dir=Path(temp_dir),
                emulator_instance=EmulatorInstance(
                    instance_id="emulator-5554",
                    adb_serial="emulator-5554",
                    appium_port=4723,
                    grpc_port=8554,
                    avd_name="AndroidWorldAvd",
                    snapshot_name="default",
                ),
                model_spec=model,
                task_payload={"task_name": "AudioRecorderRecordAudioWithFileName"},
                task_instruction="Record audio.",
                mock_mode=False,
            )
            stderr_path = request.output_dir / "raw" / "mobile_agent_e_androidworld" / "bridge_stderr.txt"
            stderr_path.parent.mkdir(parents=True, exist_ok=True)
            stderr_path.write_text("invalid action json", encoding="utf-8")

            message = bridge._format_runtime_failure(
                failure_detail={
                    "error_message": (
                        "MOBILE_AGENT_E_BRIDGE_ERROR: Mobile-Agent-E completed without any action record in "
                        "steps.json. The upstream runner reported an invalid action JSON: "
                        "{\"name\":\"Tap\", \"arguments\":{\"x\":927, 1976}}."
                    )
                },
                stderr_path=stderr_path,
                request=request,
            )

        self.assertIn("invalid action JSON", message)
        self.assertIn("runner.stdout.txt", message)

    def test_bridge_formats_operator_prompt_history_bug_clearly(self) -> None:
        bridge = MobileAgentEAndroidWorldBridgeAdapter()
        with tempfile.TemporaryDirectory() as temp_dir:
            spec = load_project_spec(PAIR_CONFIG)
            model = spec.models[0]
            request = MobileAgentEAndroidWorldRunRequest(
                trial_context=mock.Mock(),  # type: ignore[arg-type]
                output_dir=Path(temp_dir),
                emulator_instance=EmulatorInstance(
                    instance_id="emulator-5554",
                    adb_serial="emulator-5554",
                    appium_port=4723,
                    grpc_port=8554,
                    avd_name="AndroidWorldAvd",
                    snapshot_name="default",
                ),
                model_spec=model,
                task_payload={"task_name": "ClockStopWatchPausedVerify"},
                task_instruction="Pause the stopwatch.",
                mock_mode=False,
            )
            stderr_path = request.output_dir / "raw" / "mobile_agent_e_androidworld" / "bridge_stderr.txt"
            stderr_path.parent.mkdir(parents=True, exist_ok=True)
            stderr_path.write_text("list index out of range", encoding="utf-8")

            message = bridge._format_runtime_failure(
                failure_detail={
                    "error_message": "MOBILE_AGENT_E_BRIDGE_ERROR: list index out of range",
                    "traceback": "File \"MobileAgentE/agents.py\", line 435, in get_prompt",
                },
                stderr_path=stderr_path,
                request=request,
            )

        self.assertIn("upstream prompt construction crashed", message)
        self.assertIn("raw/mobile_agent_e/failure.json", message)

    def test_mirror_platform_step_artifacts_allows_existing_platform_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trial_dir = Path(temp_dir)
            steps_dir = trial_dir / "steps"
            steps_dir.mkdir(parents=True, exist_ok=True)
            screenshot = steps_dir / "0001.jpg"
            xml = steps_dir / "0001.xml"
            screenshot.write_bytes(b"jpg")
            xml.write_text("<hierarchy />", encoding="utf-8")

            payload = {
                "step_index": 1,
                "artifacts": {
                    "screenshot_path": "steps/0001.jpg",
                    "xml_path": "steps/0001.xml",
                },
                "observation": {
                    "screenshot_path": "steps/0001.jpg",
                    "xml_path": "steps/0001.xml",
                },
            }

            mirrored = runtime_module._mirror_platform_step_artifacts(
                step_payload=payload,
                trial_dir=trial_dir,
            )

            self.assertEqual(mirrored["platform_step_0001_screenshot"], "steps/0001.jpg")
            self.assertEqual(mirrored["platform_step_0001_xml"], "steps/0001.xml")
            self.assertEqual(payload["artifacts"]["screenshot_path"], "steps/0001.jpg")
            self.assertEqual(payload["artifacts"]["xml_path"], "steps/0001.xml")
