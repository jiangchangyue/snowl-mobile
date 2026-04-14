from __future__ import annotations

import contextlib
from dataclasses import dataclass
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from snowl_mobile.adapters.bridges.open_autoglm_androidworld import (
    OpenAutoGLMAndroidWorldBridgeAdapter,
    OpenAutoGLMAndroidWorldRunRequest,
    _run_bridge_subprocess,
)
from snowl_mobile.adapters.bridges import open_autoglm_androidworld as bridge_module
from snowl_mobile.adapters.bridges import open_autoglm_androidworld_runtime as runtime_module
from snowl_mobile.core.errors import IntegrationError
from snowl_mobile.devices.emulator_instance import EmulatorInstance
from snowl_mobile.models.model_spec import ModelSpec


class OpenAutoGLMAndroidWorldBridgeRuntimeTestCase(unittest.TestCase):
    def test_format_trial_start_message_includes_instruction(self) -> None:
        message = runtime_module._format_trial_start_message(
            suite_family="android_world",
            task_name="BrowserMultiply",
            task_instruction="Open the file task.html in Downloads and solve the multiplication challenge.",
        )

        self.assertEqual(
            message,
            "Starting AndroidWorld task 'BrowserMultiply' (Open the file task.html in Downloads and solve the multiplication challenge.)",
        )

    def test_format_observation_preview_compacts_visible_text(self) -> None:
        preview = runtime_module._format_observation_preview(
            {
                "parsed_text": "Back\nNew conversation\nAdd Contact or Number…\nNo contacts found",
            }
        )

        self.assertEqual(preview, "Back New conversation Add Contact or Number… No contacts found")

    def test_sanitize_model_response_strips_answer_wrappers(self) -> None:
        @dataclass
        class FakeResponse:
            thinking: str
            action: str
            raw_content: str

        response = FakeResponse(
            thinking="<think>Need to open Messages.</think><answer>",
            action='do(action="Launch", app="SimpleSMSMessenger")\n</answer>',
            raw_content=(
                "<think>Need to open Messages.</think><answer>\n"
                'do(action="Launch", app="SimpleSMSMessenger")\n'
                "</answer>"
            ),
        )

        sanitized = runtime_module._sanitize_model_response(response)

        self.assertIs(sanitized, response)
        self.assertEqual(response.thinking, "Need to open Messages.")
        self.assertEqual(response.action, 'do(action="Launch", app="SimpleSMSMessenger")')

    def test_resolve_task_instruction_prefers_androidworld_goal(self) -> None:
        class FakeTask:
            goal = "Send a text message using Simple SMS Messenger to +16597910719 with message: Beauty is in the eye of the beholder."

        instruction = runtime_module._resolve_task_instruction(
            task=FakeTask(),
            fallback_instruction="Send a text message using Simple SMS Messenger to {number} with message: {message}",
            task_name="SimpleSmsSend",
        )

        self.assertEqual(
            instruction,
            "Send a text message using Simple SMS Messenger to +16597910719 with message: Beauty is in the eye of the beholder.",
        )

    def test_write_ui_xml_persists_platform_readable_step_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "0001.xml"
            runtime_module._write_ui_xml(
                target,
                ui_elements=[
                    {
                        "text": "Add Contact or Number…",
                        "resource_id": "com.simplemobiletools.smsmessenger:id/new_conversation_address",
                        "class_name": "android.widget.EditText",
                        "is_clickable": True,
                        "is_focused": True,
                    }
                ],
                activity="com.simplemobiletools.smsmessenger/.NewConversationActivity",
                package_name="com.simplemobiletools.smsmessenger",
                screen_size="1080x2400",
            )

            self.assertTrue(target.exists())
            root = ET.fromstring(target.read_text(encoding="utf-8"))
            self.assertEqual(root.tag, "hierarchy")
            self.assertEqual(root.attrib["package"], "com.simplemobiletools.smsmessenger")
            node = root.find("node")
            self.assertIsNotNone(node)
            assert node is not None
            self.assertEqual(node.attrib["text"], "Add Contact or Number…")
            self.assertEqual(
                node.attrib["resource-id"],
                "com.simplemobiletools.smsmessenger:id/new_conversation_address",
            )
            self.assertEqual(node.attrib["clickable"], "true")

    def test_model_endpoint_failure_detection_matches_connection_errors(self) -> None:
        self.assertTrue(
            runtime_module._looks_like_model_endpoint_failure(
                "openai.APIConnectionError: Connection error. httpx.ConnectError: "
                "[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol"
            )
        )

    def test_a11y_forwarder_download_detection_matches_urlopen_errors(self) -> None:
        self.assertTrue(
            runtime_module._looks_like_a11y_forwarder_download_failure(
                "urllib.error.URLError: <urlopen error [SSL: UNEXPECTED_EOF_WHILE_READING] "
                "EOF occurred in violation of protocol (_ssl.c:1016)>"
            )
        )

    def test_bridge_subprocess_timeout_persists_failure_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            stdout_path = root / "stdout.txt"
            stderr_path = root / "stderr.txt"
            failure_path = root / "failure.json"
            timeout_error = bridge_module.subprocess.TimeoutExpired(
                cmd=["python", "-m", "bridge"],
                timeout=3,
                output=b"partial stdout",
                stderr=b"partial stderr",
            )

            with mock.patch.object(bridge_module.subprocess, "run", side_effect=timeout_error):
                with self.assertRaises(IntegrationError) as context:
                    _run_bridge_subprocess(
                        command=["python", "-m", "bridge"],
                        cwd=root,
                        env={},
                        stdout_path=stdout_path,
                        stderr_path=stderr_path,
                        failure_path=failure_path,
                        timeout_sec=3,
                        label="test bridge",
                    )

            self.assertIn("timed out after 3s", str(context.exception))
            self.assertEqual(stdout_path.read_text(encoding="utf-8"), "partial stdout")
            self.assertEqual(stderr_path.read_text(encoding="utf-8"), "partial stderr")
            self.assertIn('"error_type": "TimeoutExpired"', failure_path.read_text(encoding="utf-8"))

    def test_ensure_androidworld_accessibility_runtime_reenables_disabled_service(self) -> None:
        logger = mock.Mock()
        wrapper = mock.Mock()
        wrapper._start_a11y_services = mock.Mock()
        wrapper._enable_a11y_tree_logs = mock.Mock()
        wrapper._configure_grpc = mock.Mock()

        class FakeController:
            env = wrapper

        class FakeEnv:
            controller = FakeController()

        with mock.patch.object(runtime_module, "_android_package_installed", return_value=True):
            with mock.patch.object(
                runtime_module,
                "_android_get_secure_setting",
                side_effect=[
                    runtime_module._ANDROIDWORLD_A11Y_FORWARDER_SERVICE,
                    "0",
                    "1",
                ],
            ):
                with mock.patch.object(
                    runtime_module,
                    "_android_get_accessibility_runtime_status",
                    return_value={"enabled": True, "bound": True, "binding": False, "crashed": False, "raw_text": ""},
                ):
                    with mock.patch.object(runtime_module, "_android_put_secure_setting", return_value=True) as put_setting:
                        with mock.patch.object(runtime_module.time, "sleep", return_value=None):
                            runtime_module._ensure_androidworld_accessibility_runtime(
                                adb_path="adb",
                                adb_serial="emulator-5554",
                                trial_logger=logger,
                                env=FakeEnv(),
                                force_reconfigure=True,
                            )

        self.assertEqual(put_setting.call_count, 2)
        wrapper._start_a11y_services.assert_called_once()
        wrapper._enable_a11y_tree_logs.assert_called_once()
        wrapper._configure_grpc.assert_called_once()
        logger.info.assert_called()

    def test_ensure_androidworld_accessibility_runtime_restarts_crashed_service(self) -> None:
        logger = mock.Mock()
        wrapper = mock.Mock()
        wrapper._start_a11y_services = mock.Mock()
        wrapper._enable_a11y_tree_logs = mock.Mock()
        wrapper._configure_grpc = mock.Mock()

        class FakeController:
            env = wrapper

        class FakeEnv:
            controller = FakeController()

        with mock.patch.object(runtime_module, "_android_package_installed", return_value=True):
            with mock.patch.object(
                runtime_module,
                "_android_get_secure_setting",
                side_effect=[
                    runtime_module._ANDROIDWORLD_A11Y_FORWARDER_SERVICE,
                    "1",
                    "1",
                ],
            ):
                with mock.patch.object(
                    runtime_module,
                    "_android_get_accessibility_runtime_status",
                    side_effect=[
                        {"enabled": True, "bound": False, "binding": False, "crashed": True, "raw_text": ""},
                        {"enabled": True, "bound": True, "binding": False, "crashed": False, "raw_text": ""},
                    ],
                ):
                    with mock.patch.object(runtime_module, "_android_force_stop_package", return_value=True) as force_stop:
                        with mock.patch.object(runtime_module, "_android_delete_secure_setting", return_value=True) as delete_setting:
                            with mock.patch.object(runtime_module, "_android_put_secure_setting", return_value=True) as put_setting:
                                with mock.patch.object(runtime_module.time, "sleep", return_value=None):
                                    runtime_module._ensure_androidworld_accessibility_runtime(
                                        adb_path="adb",
                                        adb_serial="emulator-5554",
                                        trial_logger=logger,
                                        env=FakeEnv(),
                                        force_reconfigure=False,
                                    )

        force_stop.assert_called_once()
        delete_setting.assert_called_once()
        self.assertGreaterEqual(put_setting.call_count, 3)
        wrapper._start_a11y_services.assert_called_once()
        wrapper._enable_a11y_tree_logs.assert_called_once()
        wrapper._configure_grpc.assert_called_once()
        logger.warning.assert_called()

    def test_warn_if_androidworld_device_profile_unsupported_logs_sdk_warning(self) -> None:
        logger = mock.Mock()
        with mock.patch.object(
            runtime_module,
            "_probe_androidworld_device_profile",
            return_value={
                "sdk_int": "34",
                "android_release": "14",
                "avd_name": "AndroidWorldAvd",
                "product_model": "sdk_gphone64_arm64",
            },
        ):
            profile = runtime_module._warn_if_androidworld_device_profile_unsupported(
                adb_path="adb",
                adb_serial="emulator-5554",
                trial_logger=logger,
            )

        self.assertEqual(profile["sdk_int"], "34")
        logger.warning.assert_called()

    def test_setup_task_scoped_apps_recovers_after_a11y_tree_failure(self) -> None:
        class FakeController:
            def __init__(self) -> None:
                self.refresh_calls = 0

            def refresh_env(self) -> None:
                self.refresh_calls += 1

        class FakeEnv:
            def __init__(self) -> None:
                self.controller = FakeController()

        class FakeTaskType:
            app_names = ("chrome",)

        fake_env = FakeEnv()
        setup_attempts = {"count": 0}
        home_calls = {"count": 0}
        root_calls = {"count": 0}

        class FakeDeviceSetup:
            @staticmethod
            def get_app_mapping(app_name: str) -> object:
                return object()

            @staticmethod
            def maybe_install_app(app_class: object, env: object) -> None:
                return None

            @staticmethod
            def setup_app(app_class: object, env: object) -> None:
                setup_attempts["count"] += 1
                if setup_attempts["count"] == 1:
                    raise RuntimeError("Could not get a11y tree.")

        class FakeAdbUtils:
            @staticmethod
            def press_home_button(controller: object) -> None:
                home_calls["count"] += 1

            @staticmethod
            def set_root_if_needed(controller: object) -> None:
                root_calls["count"] += 1

        fake_env_module = ModuleType("android_world.env")
        fake_env_module.adb_utils = FakeAdbUtils
        fake_setup_device_module = ModuleType("android_world.env.setup_device")
        fake_setup_device_module.setup = FakeDeviceSetup

        with mock.patch.object(runtime_module, "_require_runtime_import", return_value=None):
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
                installed_apps = runtime_module._setup_task_scoped_apps(
                    task_type=FakeTaskType,
                    env=fake_env,
                    install_hint="pip install -r requirements.txt",
                )

        self.assertEqual(installed_apps, ("chrome",))
        self.assertEqual(setup_attempts["count"], 2)
        self.assertEqual(fake_env.controller.refresh_calls, 1)
        self.assertGreaterEqual(home_calls["count"], 2)
        self.assertGreaterEqual(root_calls["count"], 2)

    def test_initialize_task_treats_missing_expense_onboarding_buttons_as_recoverable(self) -> None:
        calls: list[tuple[str, str]] = []

        class FakeExpenseApp:
            app_name = "pro expense"

            @classmethod
            def setup(cls, env: object) -> None:
                del cls, env
                raise ValueError('Target text "NEXT" not found.')

        class FakeTask:
            def initialize_task(self, env: object) -> None:
                FakeExpenseApp.setup(env)

        class FakeEnv:
            controller = object()

        fake_apps_module = ModuleType("android_world.env.setup_device.apps")
        fake_apps_module.ExpenseApp = FakeExpenseApp
        fake_adb_utils_module = ModuleType("android_world.env.adb_utils")
        fake_adb_utils_module.launch_app = lambda app_name, controller: calls.append(("launch", app_name))
        fake_adb_utils_module.close_app = lambda app_name, controller: calls.append(("close", app_name))

        with mock.patch.dict(
            sys.modules,
            {
                "android_world.env.setup_device.apps": fake_apps_module,
                "android_world.env.adb_utils": fake_adb_utils_module,
            },
            clear=False,
        ):
            with mock.patch.object(runtime_module.time, "sleep", return_value=None):
                runtime_module._initialize_androidworld_task_with_contact_fallback(
                    task=FakeTask(),
                    env=FakeEnv(),
                    trial_logger=mock.Mock(),
                )

        self.assertEqual(calls, [("launch", "pro expense"), ("close", "pro expense")])

    def test_setup_task_scoped_apps_skips_reinstall_for_installed_package(self) -> None:
        class FakeController:
            def refresh_env(self) -> None:
                return None

        class FakeEnv:
            def __init__(self) -> None:
                self.controller = FakeController()

        class FakeAppClass:
            @staticmethod
            def package_name() -> str:
                return "org.example.clipper"

        class FakeTaskType:
            app_names = ("clipper",)

        setup_calls = {"count": 0}
        install_calls = {"count": 0}

        class FakeDeviceSetup:
            @staticmethod
            def get_app_mapping(app_name: str) -> object:
                return FakeAppClass

            @staticmethod
            def is_package_installed(package_name: str, env: object) -> bool:
                return package_name == "org.example.clipper"

            @staticmethod
            def maybe_install_app(app_class: object, env: object) -> None:
                install_calls["count"] += 1

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

        fake_env_module = ModuleType("android_world.env")
        fake_env_module.adb_utils = FakeAdbUtils
        fake_setup_device_module = ModuleType("android_world.env.setup_device")
        fake_setup_device_module.setup = FakeDeviceSetup

        with mock.patch.object(runtime_module, "_require_runtime_import", return_value=None):
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
                installed_apps = runtime_module._setup_task_scoped_apps(
                    task_type=FakeTaskType,
                    env=FakeEnv(),
                    install_hint="pip install -r requirements.txt",
                    adb_serial="emulator-5554",
                    trial_logger=mock.Mock(),
                )

        self.assertEqual(installed_apps, ("clipper",))
        self.assertEqual(install_calls["count"], 0)
        self.assertEqual(setup_calls["count"], 1)

    def test_setup_task_scoped_apps_reads_instance_level_app_names(self) -> None:
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

        fake_env_module = ModuleType("android_world.env")
        fake_env_module.adb_utils = FakeAdbUtils
        fake_setup_device_module = ModuleType("android_world.env.setup_device")
        fake_setup_device_module.setup = FakeDeviceSetup

        with mock.patch.object(runtime_module, "_require_runtime_import", return_value=None):
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
                installed_apps = runtime_module._setup_task_scoped_apps(
                    task_type=FakeTask(),
                    env=FakeEnv(),
                    install_hint="pip install -r requirements.txt",
                )

        self.assertEqual(installed_apps, ("joplin",))
        self.assertEqual(setup_calls["count"], 1)

    def test_sqlite_fts4_patch_falls_back_to_sqlite3_cli(self) -> None:
        @dataclass
        class FakeRow:
            title: str

        @dataclass
        class FakeInsertRow:
            title: str
            id: str = "row-1"

        class FakeSqliteUtils(ModuleType):
            @staticmethod
            def execute_query(query: str, db_path: str, row_type: type[object]) -> list[object]:
                raise RuntimeError("no such module: fts4")

            @staticmethod
            def get_rows_from_remote_device(*args: object, **kwargs: object) -> list[object]:
                raise RuntimeError("no such module: fts4")

            @staticmethod
            def delete_all_rows_from_table(*args: object, **kwargs: object) -> None:
                raise RuntimeError("no such module: fts4")

            @staticmethod
            def insert_rows_to_remote_db(*args: object, **kwargs: object) -> None:
                raise RuntimeError("no such module: fts4")

            @staticmethod
            def table_exists(*args: object, **kwargs: object) -> bool:
                return True

        class FakeController:
            def __init__(self) -> None:
                self.pushes: list[tuple[str, str, object]] = []

            @contextlib.contextmanager
            def pull_file(self, remote_path: str, timeout_sec: object = None):
                with tempfile.TemporaryDirectory() as temp_dir:
                    local_db_path = Path(temp_dir) / Path(remote_path).name
                    local_db_path.write_text("", encoding="utf-8")
                    yield temp_dir

            def push_file(self, local_path: str, remote_path: str, timeout_sec: object = None) -> None:
                self.pushes.append((local_path, remote_path, timeout_sec))

        class FakeEnv:
            def __init__(self) -> None:
                self.controller = FakeController()

        fake_sqlite_utils = FakeSqliteUtils("android_world.task_evals.utils.sqlite_utils")
        fake_schema_utils = ModuleType("android_world.task_evals.utils.sqlite_schema_utils")
        fake_schema_utils.GenericRow = FakeRow
        fake_file_utils = ModuleType("android_world.utils.file_utils")
        fake_file_utils.convert_to_posix_path = lambda directory, filename: str(Path(directory) / filename)
        fake_adb_utils = ModuleType("android_world.env.adb_utils")
        fake_adb_utils.close_app = lambda *args, **kwargs: None
        fake_adb_utils.launch_app = lambda *args, **kwargs: None
        fake_utils_pkg = ModuleType("android_world.task_evals.utils")
        fake_utils_pkg.sqlite_utils = fake_sqlite_utils
        fake_utils_pkg.sqlite_schema_utils = fake_schema_utils
        fake_android_utils_pkg = ModuleType("android_world.utils")
        fake_android_utils_pkg.file_utils = fake_file_utils
        fake_env_pkg = ModuleType("android_world.env")
        fake_env_pkg.adb_utils = fake_adb_utils

        cli_calls: list[tuple[str, bool]] = []

        def fake_run_sqlite3_cli(*, sqlite3_path: str, db_path: str | Path, sql: str, json_output: bool = False) -> str:
            cli_calls.append((sql, json_output))
            if json_output:
                return '[{"title":"To-Do List"}]'
            return ""

        with mock.patch.object(runtime_module, "_require_runtime_import", return_value=None):
            with mock.patch.object(runtime_module, "_python_sqlite_supports_fts4", return_value=False):
                with mock.patch.object(runtime_module, "_find_sqlite3_cli", return_value="/usr/bin/sqlite3"):
                    with mock.patch.object(runtime_module, "_run_sqlite3_cli", side_effect=fake_run_sqlite3_cli):
                        with mock.patch.dict(
                            sys.modules,
                            {
                                "android_world.task_evals.utils": fake_utils_pkg,
                                "android_world.task_evals.utils.sqlite_utils": fake_sqlite_utils,
                                "android_world.task_evals.utils.sqlite_schema_utils": fake_schema_utils,
                                "android_world.utils": fake_android_utils_pkg,
                                "android_world.utils.file_utils": fake_file_utils,
                                "android_world.env": fake_env_pkg,
                                "android_world.env.adb_utils": fake_adb_utils,
                            },
                            clear=False,
                        ):
                            restore = runtime_module._patch_androidworld_sqlite_fts4_support(
                                trial_logger=mock.Mock()
                            )
                            rows = fake_sqlite_utils.execute_query(
                                "SELECT * FROM folders;",
                                "/tmp/joplin.sqlite",
                                FakeRow,
                            )
                            fake_sqlite_utils.delete_all_rows_from_table(
                                "folders",
                                "/data/data/net.cozic.joplin/databases/joplin.sqlite",
                                FakeEnv(),
                                "joplin",
                            )
                            fake_sqlite_utils.insert_rows_to_remote_db(
                                [FakeInsertRow(title="Inbox")],
                                None,
                                "folders",
                                "/data/data/net.cozic.joplin/databases/joplin.sqlite",
                                "joplin",
                                FakeEnv(),
                            )
                            restore()

        self.assertEqual(rows, [FakeRow(title="To-Do List")])
        self.assertEqual(len(cli_calls), 4)
        self.assertTrue(cli_calls[0][1])
        self.assertIn("DELETE FROM folders", cli_calls[1][0])
        self.assertTrue(cli_calls[2][1])
        self.assertIn("INSERT INTO folders", cli_calls[3][0])

    def test_run_androidworld_env_operation_recovers_after_a11y_tree_failure(self) -> None:
        class FakeController:
            def __init__(self) -> None:
                self.refresh_calls = 0

            def refresh_env(self) -> None:
                self.refresh_calls += 1

        class FakeEnv:
            def __init__(self) -> None:
                self.controller = FakeController()

        fake_env = FakeEnv()
        call_count = {"count": 0}

        class FakeAdbUtils:
            @staticmethod
            def press_home_button(controller: object) -> None:
                return None

            @staticmethod
            def set_root_if_needed(controller: object) -> None:
                return None

        fake_env_module = ModuleType("android_world.env")
        fake_env_module.adb_utils = FakeAdbUtils

        def flaky_operation() -> str:
            call_count["count"] += 1
            if call_count["count"] == 1:
                raise RuntimeError("Could not get a11y tree.")
            return "ok"

        with mock.patch.dict(
            sys.modules,
            {
                "android_world.env": fake_env_module,
                "android_world.env.adb_utils": FakeAdbUtils,
            },
            clear=False,
        ):
            result = runtime_module._run_androidworld_env_operation(
                env_ref={"env": fake_env},
                trial_logger=None,
                description="unit test bootstrap",
                operation=flaky_operation,
            )

        self.assertEqual(result, "ok")
        self.assertEqual(call_count["count"], 2)
        self.assertEqual(fake_env.controller.refresh_calls, 1)

    def test_extract_androidworld_shell_date_output_keeps_last_timestamp_line(self) -> None:
        noisy_output = (
            "I0402 22:52:46.247376 5549076 ev_poll_posix.cc:593] FD from fork parent still in poll list: fd(12, generation: 1)\n"
            "I0402 22:52:46.247405 5549076 ev_poll_posix.cc:593] FD from fork parent still in poll list: fd(5, generation: 1)\n"
            "Sun Oct 15 15:34:07 UTC 2023\n"
        )

        cleaned = runtime_module._extract_androidworld_shell_date_output(noisy_output)

        self.assertEqual(cleaned, "Sun Oct 15 15:34:07 UTC 2023")

    def test_extract_androidworld_unix_timestamp_output_keeps_last_numeric_line(self) -> None:
        noisy_output = (
            "I0409 00:22:12.863188 4279192 ev_poll_posix.cc:593] FD from fork parent still in poll list: fd(12, generation: 1)\n"
            "1712622137\n"
        )

        cleaned = runtime_module._extract_androidworld_unix_timestamp_output(noisy_output)

        self.assertEqual(cleaned, "1712622137")

    def test_extract_information_retrieval_answer_text_unwraps_plain_quoted_text(self) -> None:
        raw_output = mock.Mock(
            action_text='"Call client for follow-up, Change Air Filter"',
            raw_content='"Call client for follow-up, Change Air Filter"',
            thinking="",
        )

        answer = runtime_module._extract_information_retrieval_answer_text(raw_output)

        self.assertEqual(answer, "Call client for follow-up, Change Air Filter")

    def test_cache_information_retrieval_answer_uses_finish_message(self) -> None:
        env = mock.Mock()
        action_record = mock.Mock(parsed_action={"_metadata": "finish", "message": "Blues Break 567"})

        with mock.patch.object(runtime_module, "_is_information_retrieval_task", return_value=True):
            answer = runtime_module._cache_information_retrieval_answer(
                env=env,
                task=object(),
                action_record=action_record,
                raw_output=mock.Mock(),
                trial_logger=mock.Mock(),
                step_index=1,
            )

        self.assertEqual(answer, "Blues Break 567")
        self.assertEqual(env.interaction_cache, "Blues Break 567")

    def test_sqlite_fallback_detection_accepts_fts3_and_fts4(self) -> None:
        self.assertTrue(runtime_module._sqlite_cli_fallback_required(RuntimeError("no such module: FTS3")))
        self.assertTrue(runtime_module._sqlite_cli_fallback_required(RuntimeError("no such module: fts4")))
        self.assertFalse(runtime_module._sqlite_cli_fallback_required(RuntimeError("database is locked")))

    def test_sqlite_missing_table_detection_matches_upstream_error(self) -> None:
        self.assertTrue(runtime_module._sqlite_missing_table_error(RuntimeError("no such table: expense")))
        self.assertFalse(runtime_module._sqlite_missing_table_error(RuntimeError("no such module: fts4")))

    def test_sqlite_missing_db_path_detection_matches_upstream_error(self) -> None:
        self.assertTrue(
            runtime_module._sqlite_missing_db_path_error(
                FileNotFoundError("/data/data/org.videolan.vlc/app_db does not exist.")
            )
        )
        self.assertFalse(runtime_module._sqlite_missing_db_path_error(RuntimeError("database is locked")))

    def test_augment_androidworld_task_setup_app_names_adds_contacts_for_sms_tasks(self) -> None:
        app_names = runtime_module._augment_androidworld_task_setup_app_names(("simple sms messenger", "phone"))

        self.assertEqual(app_names, ("simple sms messenger", "phone", "contacts"))

    def test_run_androidworld_task_bootstrap_with_recovery_retries_ui_failures(self) -> None:
        env_ref = {"env": object()}
        call_count = {"count": 0}
        refresh_calls: list[str] = []
        reload_calls = {"count": 0}

        def bootstrap_operation() -> str:
            call_count["count"] += 1
            if call_count["count"] == 1:
                raise ValueError('Target text "SAVE" not found.')
            return "ok"

        def refresh_bootstrap_state() -> None:
            refresh_calls.append("refresh")

        def reload_env() -> object:
            reload_calls["count"] += 1
            env_ref["env"] = object()
            return env_ref["env"]

        with mock.patch.object(
            runtime_module,
            "_run_androidworld_env_operation",
            side_effect=lambda **kwargs: kwargs["operation"](),
        ):
            result = runtime_module._run_androidworld_task_bootstrap_with_recovery(
                env_ref=env_ref,
                trial_logger=mock.Mock(),
                task_name="SimpleSmsResend",
                bootstrap_operation=bootstrap_operation,
                refresh_bootstrap_state=refresh_bootstrap_state,
                reload_env=reload_env,
            )

        self.assertEqual(result, "ok")
        self.assertEqual(call_count["count"], 2)
        self.assertEqual(refresh_calls, ["refresh"])
        self.assertEqual(reload_calls["count"], 1)

    def test_run_androidworld_task_bootstrap_with_recovery_retries_sqlite_reinit_failures(self) -> None:
        env_ref = {"env": object()}
        call_count = {"count": 0}
        refresh_calls: list[str] = []

        def bootstrap_operation() -> str:
            call_count["count"] += 1
            if call_count["count"] == 1:
                raise RuntimeError("After clearing the old SQLite database, a new empty database was not created.")
            return "ok"

        def refresh_bootstrap_state() -> None:
            refresh_calls.append("refresh")

        with mock.patch.object(
            runtime_module,
            "_run_androidworld_env_operation",
            side_effect=lambda **kwargs: kwargs["operation"](),
        ):
            result = runtime_module._run_androidworld_task_bootstrap_with_recovery(
                env_ref=env_ref,
                trial_logger=mock.Mock(),
                task_name="ExpenseAddMultiple",
                bootstrap_operation=bootstrap_operation,
                refresh_bootstrap_state=refresh_bootstrap_state,
            )

        self.assertEqual(result, "ok")
        self.assertEqual(call_count["count"], 2)
        self.assertEqual(refresh_calls, ["refresh"])

    def test_insert_androidworld_contact_via_provider_populates_name_and_phone_rows(self) -> None:
        issued_commands: list[tuple[str, ...]] = []
        raw_contact_queries = iter(
            [
                "No result found.\n",
                "Row: 0 _id=7\n",
            ]
        )

        adb_utils_module = ModuleType("android_world.env.adb_utils")

        def fake_issue_generic_request(args: object, env: object) -> object:
            command = tuple(args)
            issued_commands.append(command)
            if command[:5] == (
                "shell",
                "content",
                "query",
                "--uri",
                "content://com.android.contacts/raw_contacts",
            ):
                output = next(raw_contact_queries)
            else:
                output = ""
            return SimpleNamespace(generic=SimpleNamespace(output=output.encode("utf-8")))

        adb_utils_module.issue_generic_request = fake_issue_generic_request  # type: ignore[attr-defined]
        adb_utils_module.check_ok = mock.Mock()  # type: ignore[attr-defined]

        contacts_utils_module = ModuleType("android_world.utils.contacts_utils")
        contacts_utils_module.clean_phone_number = lambda value: "".join(ch for ch in str(value) if ch.isdigit())  # type: ignore[attr-defined]
        contacts_utils_module.list_contacts = lambda env: [  # type: ignore[attr-defined]
            SimpleNamespace(name="Noa Mohammed", number="15551234567")
        ]

        def fake_import_module(name: str) -> ModuleType:
            if name == "android_world.env.adb_utils":
                return adb_utils_module
            if name == "android_world.utils.contacts_utils":
                return contacts_utils_module
            raise AssertionError(name)

        with mock.patch.object(runtime_module.importlib, "import_module", side_effect=fake_import_module):
            with mock.patch.object(runtime_module.time, "sleep", return_value=None):
                details = runtime_module._insert_androidworld_contact_via_provider(
                    name="Noa Mohammed",
                    phone_number="+1 555 123 4567",
                    env=object(),
                )

        self.assertEqual(details["method"], "content_provider_insert")
        self.assertEqual(details["raw_contact_id"], 7)
        self.assertIn(
            (
                "shell",
                "content",
                "insert",
                "--uri",
                "content://com.android.contacts/data",
                "--bind",
                "raw_contact_id:i:7",
                "--bind",
                "mimetype:s:vnd.android.cursor.item/name",
                "--bind",
                "data1:s:Noa Mohammed",
            ),
            issued_commands,
        )
        self.assertIn(
            (
                "shell",
                "content",
                "insert",
                "--uri",
                "content://com.android.contacts/data",
                "--bind",
                "raw_contact_id:i:7",
                "--bind",
                "mimetype:s:vnd.android.cursor.item/phone_v2",
                "--bind",
                "data1:s:+1 555 123 4567",
                "--bind",
                "data2:i:2",
            ),
            issued_commands,
        )

    def test_sqlite_fts4_patch_recovers_missing_remote_db_path_without_crashing(self) -> None:
        class FakeSqliteUtils(ModuleType):
            @staticmethod
            def execute_query(query: str, db_path: str, row_type: type[object]) -> list[object]:
                return []

            @staticmethod
            def get_rows_from_remote_device(*args: object, **kwargs: object) -> list[object]:
                return []

            @staticmethod
            def delete_all_rows_from_table(*args: object, **kwargs: object) -> None:
                raise FileNotFoundError("/data/data/org.videolan.vlc/app_db does not exist.")

            @staticmethod
            def insert_rows_to_remote_db(*args: object, **kwargs: object) -> None:
                return None

            @staticmethod
            def table_exists(*args: object, **kwargs: object) -> bool:
                return False

        class FakeController:
            @contextlib.contextmanager
            def pull_file(self, remote_path: str, timeout_sec: object = None):
                raise AssertionError("delete_all_rows_from_table should return before pulling a missing DB path")
                yield  # pragma: no cover

            def push_file(self, local_path: str, remote_path: str, timeout_sec: object = None) -> None:
                return None

        class FakeEnv:
            def __init__(self) -> None:
                self.controller = FakeController()

        fake_sqlite_utils = FakeSqliteUtils("android_world.task_evals.utils.sqlite_utils")
        fake_schema_utils = ModuleType("android_world.task_evals.utils.sqlite_schema_utils")
        fake_schema_utils.GenericRow = object
        fake_file_utils = ModuleType("android_world.utils.file_utils")
        fake_file_utils.convert_to_posix_path = lambda directory, filename: str(Path(directory) / filename)
        fake_adb_utils = ModuleType("android_world.env.adb_utils")
        fake_adb_utils.close_app = lambda *args, **kwargs: None
        fake_adb_utils.launch_app = lambda *args, **kwargs: None
        fake_utils_pkg = ModuleType("android_world.task_evals.utils")
        fake_utils_pkg.sqlite_utils = fake_sqlite_utils
        fake_utils_pkg.sqlite_schema_utils = fake_schema_utils
        fake_android_utils_pkg = ModuleType("android_world.utils")
        fake_android_utils_pkg.file_utils = fake_file_utils
        fake_env_pkg = ModuleType("android_world.env")
        fake_env_pkg.adb_utils = fake_adb_utils

        with mock.patch.object(runtime_module, "_require_runtime_import", return_value=None):
            with mock.patch.object(runtime_module, "_python_sqlite_supports_fts4", return_value=False):
                with mock.patch.object(runtime_module, "_find_sqlite3_cli", return_value="/usr/bin/sqlite3"):
                    with mock.patch.object(
                        runtime_module,
                        "_initialize_androidworld_sqlite_owner_app",
                        return_value="setup_app",
                    ) as initialize_owner_app:
                        with mock.patch.dict(
                            sys.modules,
                            {
                                "android_world.task_evals.utils": fake_utils_pkg,
                                "android_world.task_evals.utils.sqlite_utils": fake_sqlite_utils,
                                "android_world.task_evals.utils.sqlite_schema_utils": fake_schema_utils,
                                "android_world.utils": fake_android_utils_pkg,
                                "android_world.utils.file_utils": fake_file_utils,
                                "android_world.env": fake_env_pkg,
                                "android_world.env.adb_utils": fake_adb_utils,
                            },
                            clear=False,
                        ):
                            restore = runtime_module._patch_androidworld_sqlite_fts4_support(
                                trial_logger=mock.Mock()
                            )
                            try:
                                fake_sqlite_utils.delete_all_rows_from_table(
                                    "Playlist",
                                    "/data/data/org.videolan.vlc/app_db/vlc_media.db",
                                    FakeEnv(),
                                    "vlc",
                                )
                            finally:
                                restore()

        initialize_owner_app.assert_called_once()

    def test_sqlite_fts4_patch_reinitializes_owner_app_when_cleared_db_is_not_readable(self) -> None:
        class FakeSqliteUtils(ModuleType):
            @staticmethod
            def execute_query(query: str, db_path: str, row_type: type[object]) -> list[object]:
                return []

            @staticmethod
            def get_rows_from_remote_device(*args: object, **kwargs: object) -> list[object]:
                return []

            @staticmethod
            def delete_all_rows_from_table(*args: object, **kwargs: object) -> None:
                return None

            @staticmethod
            def insert_rows_to_remote_db(*args: object, **kwargs: object) -> None:
                return None

            @staticmethod
            def table_exists(*args: object, **kwargs: object) -> bool:
                return True

        class FakeController:
            def __init__(self) -> None:
                self.pull_calls = 0

            @contextlib.contextmanager
            def pull_file(self, remote_path: str, timeout_sec: object = None):
                self.pull_calls += 1
                if self.pull_calls == 1:
                    raise FileNotFoundError(
                        "/data/data/com.arduia.expense/databases/accounting.db does not exist."
                    )
                with tempfile.TemporaryDirectory() as local_dir:
                    yield local_dir

            def push_file(self, local_path: str, remote_path: str, timeout_sec: object = None) -> None:
                return None

        class FakeEnv:
            def __init__(self) -> None:
                self.controller = FakeController()

        fake_sqlite_utils = FakeSqliteUtils("android_world.task_evals.utils.sqlite_utils")
        fake_schema_utils = ModuleType("android_world.task_evals.utils.sqlite_schema_utils")
        fake_schema_utils.GenericRow = object
        fake_file_utils = ModuleType("android_world.utils.file_utils")
        fake_file_utils.convert_to_posix_path = lambda directory, filename: str(Path(directory) / filename)
        fake_adb_utils = ModuleType("android_world.env.adb_utils")
        fake_adb_utils.close_app = lambda *args, **kwargs: None
        fake_adb_utils.launch_app = lambda *args, **kwargs: None
        fake_utils_pkg = ModuleType("android_world.task_evals.utils")
        fake_utils_pkg.sqlite_utils = fake_sqlite_utils
        fake_utils_pkg.sqlite_schema_utils = fake_schema_utils
        fake_android_utils_pkg = ModuleType("android_world.utils")
        fake_android_utils_pkg.file_utils = fake_file_utils
        fake_env_pkg = ModuleType("android_world.env")
        fake_env_pkg.adb_utils = fake_adb_utils

        with mock.patch.object(runtime_module, "_require_runtime_import", return_value=None):
            with mock.patch.object(runtime_module, "_python_sqlite_supports_fts4", return_value=False):
                with mock.patch.object(runtime_module, "_find_sqlite3_cli", return_value="/usr/bin/sqlite3"):
                    with mock.patch.object(
                        runtime_module,
                        "_initialize_androidworld_sqlite_owner_app",
                        return_value="setup_app",
                    ) as initialize_owner_app:
                        with mock.patch.dict(
                            sys.modules,
                            {
                                "android_world.task_evals.utils": fake_utils_pkg,
                                "android_world.task_evals.utils.sqlite_utils": fake_sqlite_utils,
                                "android_world.task_evals.utils.sqlite_schema_utils": fake_schema_utils,
                                "android_world.utils": fake_android_utils_pkg,
                                "android_world.utils.file_utils": fake_file_utils,
                                "android_world.env": fake_env_pkg,
                                "android_world.env.adb_utils": fake_adb_utils,
                            },
                            clear=False,
                        ):
                            restore = runtime_module._patch_androidworld_sqlite_fts4_support(
                                trial_logger=mock.Mock()
                            )
                            try:
                                fake_sqlite_utils.delete_all_rows_from_table(
                                    "expense",
                                    "/data/data/com.arduia.expense/databases/accounting.db",
                                    FakeEnv(),
                                    "pro expense",
                                )
                            finally:
                                restore()

        initialize_owner_app.assert_called_once()

    def test_initialize_androidworld_task_with_contact_fallback_uses_provider_on_recoverable_error(self) -> None:
        contacts_utils_module = ModuleType("android_world.utils.contacts_utils")

        def failing_add_contact(name: str, phone_number: str, env: object, ui_delay_sec: float = 1.0) -> None:
            raise ValueError("Invalid element index: 1, must be between 0 and -1.")

        contacts_utils_module.add_contact = failing_add_contact  # type: ignore[attr-defined]

        class FakeTask:
            def initialize_task(self, env: object) -> None:
                contacts_utils_module.add_contact("Noa Mohammed", "+1 555 123 4567", getattr(env, "controller", env))

        fake_env = SimpleNamespace(controller=object())
        trial_logger = mock.Mock()

        with mock.patch.object(
            runtime_module.importlib,
            "import_module",
            side_effect=lambda name: contacts_utils_module if name == "android_world.utils.contacts_utils" else None,
        ):
            with mock.patch.object(
                runtime_module,
                "_insert_androidworld_contact_via_provider",
                return_value={"method": "content_provider_insert", "raw_contact_id": 7},
            ) as fallback_mock:
                runtime_module._initialize_androidworld_task_with_contact_fallback(
                    task=FakeTask(),
                    env=fake_env,
                    trial_logger=trial_logger,
                )

        fallback_mock.assert_called_once_with(
            name="Noa Mohammed",
            phone_number="+1 555 123 4567",
            env=fake_env.controller,
        )
        trial_logger.warning.assert_called()
        trial_logger.info.assert_called()

    def test_score_androidworld_task_with_missing_table_recovery_retries_after_app_launch(self) -> None:
        class FakeTask:
            app_names = ["retro music"]

            def __init__(self) -> None:
                self.calls = 0

            def is_successful(self, env: object) -> float:
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("no such table: playing_queue")
                return 1.0

        notes: list[str] = []
        task = FakeTask()

        with mock.patch.object(
            runtime_module,
            "_run_androidworld_env_operation",
            side_effect=lambda **kwargs: kwargs["operation"](),
        ):
            with mock.patch.object(
                runtime_module,
                "_initialize_androidworld_task_apps_for_scoring",
                return_value=("retro music",),
            ) as initialize_apps:
                result = runtime_module._score_androidworld_task_with_missing_table_recovery(
                    task=task,
                    task_name="RetroPlayingQueue",
                    env_ref={"env": mock.Mock(controller=object())},
                    trial_logger=mock.Mock(),
                    notes=notes,
                )

        self.assertEqual(result, 1.0)
        initialize_apps.assert_called_once()
        self.assertEqual(task.calls, 2)
        self.assertTrue(any("retro music" in note.lower() for note in notes))

    def test_score_androidworld_task_with_missing_table_recovery_records_task_failure_after_retry(self) -> None:
        class FakeTask:
            app_names = ["retro music"]

            def is_successful(self, env: object) -> float:
                raise RuntimeError("no such table: playing_queue")

        notes: list[str] = []

        with mock.patch.object(
            runtime_module,
            "_run_androidworld_env_operation",
            side_effect=lambda **kwargs: kwargs["operation"](),
        ):
            with mock.patch.object(
                runtime_module,
                "_initialize_androidworld_task_apps_for_scoring",
                return_value=("retro music",),
            ) as initialize_apps:
                result = runtime_module._score_androidworld_task_with_missing_table_recovery(
                    task=FakeTask(),
                    task_name="RetroPlayingQueue",
                    env_ref={"env": mock.Mock(controller=object())},
                    trial_logger=mock.Mock(),
                    notes=notes,
                )

        self.assertEqual(result, 0.0)
        initialize_apps.assert_called_once()
        self.assertTrue(any("unsuccessful" in note.lower() for note in notes))

    def test_score_androidworld_task_with_missing_db_path_recovery_records_task_failure_after_retry(self) -> None:
        class FakeTask:
            app_names = ["vlc"]

            def is_successful(self, env: object) -> float:
                raise FileNotFoundError("/data/data/org.videolan.vlc/app_db does not exist.")

        notes: list[str] = []

        with mock.patch.object(
            runtime_module,
            "_run_androidworld_env_operation",
            side_effect=lambda **kwargs: kwargs["operation"](),
        ):
            with mock.patch.object(
                runtime_module,
                "_initialize_androidworld_task_apps_for_scoring",
                return_value=("vlc",),
            ) as initialize_apps:
                result = runtime_module._score_androidworld_task_with_missing_table_recovery(
                    task=FakeTask(),
                    task_name="VlcCreatePlaylist",
                    env_ref={"env": mock.Mock(controller=object())},
                    trial_logger=mock.Mock(),
                    notes=notes,
                )

        self.assertEqual(result, 0.0)
        initialize_apps.assert_called_once()
        self.assertTrue(any("unsuccessful" in note.lower() for note in notes))

    def test_score_androidworld_task_with_remote_read_retry_exhaustion_records_task_failure_after_retry(self) -> None:
        class FakeTask:
            app_names = ["pro expense"]

            def is_successful(self, env: object) -> float:
                raise ValueError(
                    "Failed to retrieve rows from expense from "
                    "/data/data/com.arduia.expense/databases/accounting.db after 3 retries. "
                    "Try increasing the number of retries."
                )

        notes: list[str] = []

        with mock.patch.object(
            runtime_module,
            "_run_androidworld_env_operation",
            side_effect=lambda **kwargs: kwargs["operation"](),
        ):
            with mock.patch.object(
                runtime_module,
                "_initialize_androidworld_task_apps_for_scoring",
                return_value=("pro expense",),
            ) as initialize_apps:
                result = runtime_module._score_androidworld_task_with_missing_table_recovery(
                    task=FakeTask(),
                    task_name="ExpenseAddMultiple",
                    env_ref={"env": mock.Mock(controller=object())},
                    trial_logger=mock.Mock(),
                    notes=notes,
                )

        self.assertEqual(result, 0.0)
        initialize_apps.assert_called_once()
        self.assertTrue(any("unsuccessful" in note.lower() for note in notes))

    def test_score_androidworld_task_with_missing_table_recovery_reraises_other_sqlite_errors(self) -> None:
        class FakeTask:
            def is_successful(self, env: object) -> float:
                raise RuntimeError("database is locked")

        with mock.patch.object(
            runtime_module,
            "_run_androidworld_env_operation",
            side_effect=lambda **kwargs: kwargs["operation"](),
        ):
            with self.assertRaisesRegex(RuntimeError, "database is locked"):
                runtime_module._score_androidworld_task_with_missing_table_recovery(
                    task=FakeTask(),
                    task_name="RetroPlayingQueue",
                    env_ref={"env": mock.Mock(controller=object())},
                    trial_logger=mock.Mock(),
                    notes=[],
                )


class OpenAutoGLMAndroidWorldBridgeFormattingTestCase(unittest.TestCase):
    def _request(self, *, output_dir: Path) -> OpenAutoGLMAndroidWorldRunRequest:
        return OpenAutoGLMAndroidWorldRunRequest(
            trial_context=None,  # type: ignore[arg-type]
            output_dir=output_dir,
            emulator_instance=EmulatorInstance(
                instance_id="emulator-5554",
                adb_serial="emulator-5554",
                appium_port=4723,
                grpc_port=8554,
                avd_name="AndroidWorldAvd",
                snapshot_name="default",
            ),
            model_spec=ModelSpec(
                model_id="qwen2.5-vl-72b-instruct",
                provider="openai_compatible",
                api_style="chat_completions",
                modalities=("text", "image"),
                supports_image_input=True,
            ),
            task_payload={"task_name": "SimpleSmsSend"},
            task_instruction="Send a text message.",
            mock_mode=False,
        )

    def test_format_runtime_failure_surfaces_model_endpoint_message(self) -> None:
        bridge = OpenAutoGLMAndroidWorldBridgeAdapter()
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            stderr_path = output_dir / "raw" / "open_autoglm_androidworld" / "bridge_stderr.txt"
            stderr_path.parent.mkdir(parents=True, exist_ok=True)
            stderr_path.write_text("ssl eof", encoding="utf-8")
            message = bridge._format_runtime_failure(
                failure_detail={
                    "error_message": (
                        "MODEL_API_ERROR: Open-AutoGLM could not reach the configured model endpoint. "
                        "Detail: openai.APIConnectionError: Connection error."
                    )
                },
                stderr_path=stderr_path,
                request=self._request(output_dir=output_dir),
            )

            self.assertIn("could not reach the configured model endpoint", message)
            self.assertIn("PHONE_AGENT_BASE_URL", message)

    def test_format_runtime_failure_surfaces_a11y_forwarder_message(self) -> None:
        bridge = OpenAutoGLMAndroidWorldBridgeAdapter()
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            stderr_path = output_dir / "raw" / "open_autoglm_androidworld" / "bridge_stderr.txt"
            stderr_path.parent.mkdir(parents=True, exist_ok=True)
            stderr_path.write_text("urlopen error", encoding="utf-8")
            message = bridge._format_runtime_failure(
                failure_detail={
                    "error_message": (
                        "ANDROIDWORLD_ENV_ERROR: failed to install or refresh the AndroidWorld accessibility "
                        "forwarder APK. Original error: <urlopen error [SSL: UNEXPECTED_EOF_WHILE_READING]>"
                    )
                },
                stderr_path=stderr_path,
                request=self._request(output_dir=output_dir),
            )

            self.assertIn("accessibility forwarder APK", message)
            self.assertIn("storage.googleapis.com", message)

    def test_format_runtime_failure_surfaces_task_app_install_message(self) -> None:
        bridge = OpenAutoGLMAndroidWorldBridgeAdapter()
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            stderr_path = output_dir / "raw" / "open_autoglm_androidworld" / "bridge_stderr.txt"
            stderr_path.parent.mkdir(parents=True, exist_ok=True)
            stderr_path.write_text("clipper download failed", encoding="utf-8")
            message = bridge._format_runtime_failure(
                failure_detail={
                    "error_message": (
                        "ANDROIDWORLD_APP_INSTALL_ERROR: failed to download or install the AndroidWorld task app "
                        "'clipper'. Original error: Failed to download and install APK for clipper"
                    )
                },
                stderr_path=stderr_path,
                request=self._request(output_dir=output_dir),
            )

        self.assertIn("task-scoped app setup failed", message)
        self.assertIn("storage.googleapis.com/gresearch/android_world", message)

    def test_format_runtime_failure_surfaces_noisy_shell_date_message(self) -> None:
        bridge = OpenAutoGLMAndroidWorldBridgeAdapter()
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            stderr_path = output_dir / "raw" / "open_autoglm_androidworld" / "bridge_stderr.txt"
            stderr_path.parent.mkdir(parents=True, exist_ok=True)
            stderr_path.write_text("time data mismatch", encoding="utf-8")
            message = bridge._format_runtime_failure(
                failure_detail={
                    "error_message": (
                        "AUTOGLM_BRIDGE_ERROR: unexpected bridge runtime failure: time data "
                        "'I0402 ... Sun Oct 15 15:34:07 UTC 2023' does not match format '%a %b %d %H:%M:%S %Z %Y'"
                    )
                },
                stderr_path=stderr_path,
                request=self._request(output_dir=output_dir),
            )

        self.assertIn("parsing the device time", message)

    def test_format_runtime_failure_surfaces_invalid_task_discovery_message(self) -> None:
        bridge = OpenAutoGLMAndroidWorldBridgeAdapter()
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            stderr_path = output_dir / "raw" / "open_autoglm_androidworld" / "bridge_stderr.txt"
            stderr_path.parent.mkdir(parents=True, exist_ok=True)
            stderr_path.write_text("failed to resolve task", encoding="utf-8")
            message = bridge._format_runtime_failure(
                failure_detail={
                    "error_message": (
                        "ANDROIDWORLD_TASK_ERROR: failed to resolve task 'time' in suite 'android_world': 'time'"
                    )
                },
                stderr_path=stderr_path,
                request=self._request(output_dir=output_dir),
            )

        self.assertIn("task discovery selected a task name", message)
        self.assertIn("information-retrieval textproto", message)


if __name__ == "__main__":
    unittest.main()
