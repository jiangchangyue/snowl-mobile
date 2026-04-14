from __future__ import annotations

import base64
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from snowl_mobile.adapters.agents import mobile_agent_e_runner


class MobileAgentERunnerLightweightTestCase(unittest.TestCase):
    def test_copy_xml_sidecar_skips_same_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            screenshot_path = Path(temp_dir) / "screenshot.png"
            xml_path = screenshot_path.with_suffix(".xml")
            screenshot_path.write_bytes(b"png")
            xml_path.write_text("<hierarchy />\n", encoding="utf-8")

            mobile_agent_e_runner._copy_xml_sidecar_if_present(  # noqa: SLF001
                screenshot_path,
                screenshot_path,
            )

            self.assertEqual(xml_path.read_text(encoding="utf-8"), "<hierarchy />\n")

    def test_image_proxy_supports_context_manager_usage(self) -> None:
        calls: list[str] = []

        class FakeImage:
            def __enter__(self) -> "FakeImage":
                calls.append("enter")
                return self

            def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
                calls.append("exit")
                return False

            def verify(self) -> None:
                calls.append("verify")

            def convert(self, mode: str) -> "FakeImage":
                calls.append(f"convert:{mode}")
                return self

            def save(self, destination: str | Path, *args: object, **kwargs: object) -> None:
                del args, kwargs
                calls.append(f"save:{Path(destination).name}")

        proxy = mobile_agent_e_runner._ImageProxy(  # noqa: SLF001
            FakeImage(),
            source_path=Path("screenshot") / "source.png",
        )

        with proxy as image:
            image.verify()
            image.convert("RGB").save(Path("tmp.png"), "PNG")

        self.assertEqual(calls, ["enter", "verify", "convert:RGB", "save:tmp.png", "exit"])

    def test_image_helpers_accept_png_bytes_with_png_name(self) -> None:
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "screenshot.png"
            destination_path = Path(temp_dir) / "normalized.png"
            source_path.write_bytes(png_bytes)

            self.assertTrue(mobile_agent_e_runner._is_valid_image_file(source_path))  # noqa: SLF001
            self.assertTrue(
                mobile_agent_e_runner._save_image_as_png(  # noqa: SLF001
                    source_path,
                    destination_path,
                )
            )
            self.assertTrue(mobile_agent_e_runner._is_valid_image_file(destination_path))  # noqa: SLF001
            self.assertGreater(
                len(mobile_agent_e_runner._encode_image_file_as_png_base64(destination_path)),  # noqa: SLF001
                0,
            )

    def test_screenshot_candidate_scan_accepts_png_bytes_named_jpg(self) -> None:
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            screenshot_dir = Path(temp_dir) / "screenshot"
            screenshot_dir.mkdir()
            source_path = screenshot_dir / "screenshot.jpg"
            destination_path = screenshot_dir / "screenshot.png"
            source_path.write_bytes(png_bytes)

            result = mobile_agent_e_runner._materialize_first_valid_screenshot_candidate(  # noqa: SLF001
                adb_path="adb",
                screenshot_dir=screenshot_dir,
                screenshot_path=destination_path,
            )

            self.assertEqual(result, destination_path)
            self.assertTrue(mobile_agent_e_runner._is_valid_image_file(destination_path))  # noqa: SLF001

    def test_screenshot_capture_falls_back_to_device_file_pull(self) -> None:
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
        )

        def fake_run(command: str, **kwargs: object) -> object:  # noqa: ARG001
            if "exec-out screencap -p" in command:
                return types.SimpleNamespace(returncode=1, stdout=b"", stderr=b"")
            if "shell screencap -p" in command:
                return types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
            if " pull " in command:
                pulled_path = Path(command.rsplit(" ", 1)[-1])
                pulled_path.write_bytes(png_bytes)
                return types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
            return types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "snowl_mobile.adapters.agents.mobile_agent_e_runner.subprocess.run",
            side_effect=fake_run,
        ), patch(
            "snowl_mobile.adapters.agents.mobile_agent_e_runner._dump_ui_hierarchy_xml",
            return_value=None,
        ):
            screenshot_path = Path(temp_dir) / "screenshot" / "screenshot.png"
            result = mobile_agent_e_runner._capture_screenshot_with_fallback(  # noqa: SLF001
                types.SimpleNamespace(SCREENSHOT_DIR=str(screenshot_path.parent)),
                "adb -s emulator-5554",
                screenshot_path=screenshot_path,
            )

            self.assertEqual(result, screenshot_path)
            self.assertTrue(mobile_agent_e_runner._is_valid_image_file(screenshot_path))  # noqa: SLF001

    def test_screenshot_capture_retries_after_transient_capture_failure(self) -> None:
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
        )
        exec_out_calls = {"count": 0}

        def fake_run(command: str, **kwargs: object) -> object:  # noqa: ARG001
            if "exec-out screencap -p" in command:
                exec_out_calls["count"] += 1
                if exec_out_calls["count"] < 4:
                    return types.SimpleNamespace(returncode=1, stdout=b"", stderr=b"exec-out failed")
                return types.SimpleNamespace(returncode=0, stdout=png_bytes, stderr=b"")
            if "shell screencap -p" in command:
                return types.SimpleNamespace(returncode=1, stdout=b"", stderr=b"device screencap failed")
            if "get-state" in command:
                return types.SimpleNamespace(returncode=0, stdout="device\n", stderr="")
            if "shell getprop sys.boot_completed" in command:
                return types.SimpleNamespace(returncode=0, stdout="1\n", stderr="")
            if "shell wm size" in command:
                return types.SimpleNamespace(returncode=0, stdout="Physical size: 1080x2400\n", stderr="")
            return types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "snowl_mobile.adapters.agents.mobile_agent_e_runner.subprocess.run",
            side_effect=fake_run,
        ), patch(
            "snowl_mobile.adapters.agents.mobile_agent_e_runner._dump_ui_hierarchy_xml",
            return_value=None,
        ), patch(
            "snowl_mobile.adapters.agents.mobile_agent_e_runner.time.sleep",
            return_value=None,
        ):
            screenshot_path = Path(temp_dir) / "screenshot" / "screenshot.png"
            result = mobile_agent_e_runner._capture_screenshot_with_fallback(  # noqa: SLF001
                types.SimpleNamespace(SCREENSHOT_DIR=str(screenshot_path.parent)),
                "adb -s emulator-5554",
                screenshot_path=screenshot_path,
            )

            self.assertEqual(result, screenshot_path)
            self.assertTrue(mobile_agent_e_runner._is_valid_image_file(screenshot_path))  # noqa: SLF001
            self.assertGreaterEqual(exec_out_calls["count"], 4)

    def test_screenshot_capture_failure_includes_recent_diagnostics(self) -> None:
        def fake_run(command: str, **kwargs: object) -> object:  # noqa: ARG001
            if "exec-out screencap -p" in command:
                return types.SimpleNamespace(returncode=1, stdout=b"", stderr=b"exec-out failed")
            if "shell screencap -p" in command:
                return types.SimpleNamespace(returncode=1, stdout=b"", stderr=b"device screencap failed")
            if "get-state" in command:
                return types.SimpleNamespace(returncode=0, stdout="device\n", stderr="")
            if "shell getprop sys.boot_completed" in command:
                return types.SimpleNamespace(returncode=0, stdout="1\n", stderr="")
            if "shell wm size" in command:
                return types.SimpleNamespace(returncode=0, stdout="Physical size: 1080x2400\n", stderr="")
            return types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "snowl_mobile.adapters.agents.mobile_agent_e_runner.subprocess.run",
            side_effect=fake_run,
        ), patch(
            "snowl_mobile.adapters.agents.mobile_agent_e_runner.time.sleep",
            return_value=None,
        ):
            screenshot_path = Path(temp_dir) / "screenshot" / "screenshot.png"
            with self.assertRaises(RuntimeError) as context:
                mobile_agent_e_runner._capture_screenshot_with_fallback(  # noqa: SLF001
                    types.SimpleNamespace(SCREENSHOT_DIR=str(screenshot_path.parent)),
                    "adb -s emulator-5554",
                    screenshot_path=screenshot_path,
                )

        self.assertIn("Last diagnostics:", str(context.exception))
        self.assertIn("exec-out screencap failed", str(context.exception))

    def test_screenshot_capture_reuses_last_valid_local_image_when_device_is_healthy(self) -> None:
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
        )

        def fake_run(command: str, **kwargs: object) -> object:  # noqa: ARG001
            if "exec-out screencap -p" in command:
                return types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
            if "shell screencap -p" in command:
                return types.SimpleNamespace(returncode=1, stdout=b"", stderr=b"exit code 1")
            if "get-state" in command:
                return types.SimpleNamespace(returncode=0, stdout="device\n", stderr="")
            if "shell getprop sys.boot_completed" in command:
                return types.SimpleNamespace(returncode=0, stdout="1\n", stderr="")
            if "shell wm size" in command:
                return types.SimpleNamespace(returncode=0, stdout="Physical size: 1080x2400\n", stderr="")
            return types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "snowl_mobile.adapters.agents.mobile_agent_e_runner.subprocess.run",
            side_effect=fake_run,
        ), patch(
            "snowl_mobile.adapters.agents.mobile_agent_e_runner._dump_ui_hierarchy_xml",
            return_value=None,
        ), patch(
            "snowl_mobile.adapters.agents.mobile_agent_e_runner.time.sleep",
            return_value=None,
        ):
            screenshot_path = Path(temp_dir) / "screenshot" / "screenshot.png"
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            screenshot_path.write_bytes(png_bytes)

            result = mobile_agent_e_runner._capture_screenshot_with_fallback(  # noqa: SLF001
                types.SimpleNamespace(SCREENSHOT_DIR=str(screenshot_path.parent)),
                "adb -s emulator-5554",
                screenshot_path=screenshot_path,
            )

            self.assertEqual(result, screenshot_path)
            self.assertTrue(mobile_agent_e_runner._is_valid_image_file(screenshot_path))  # noqa: SLF001

    def test_screenshot_capture_does_not_reuse_stale_image_when_device_is_unhealthy(self) -> None:
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
        )

        def fake_run(command: str, **kwargs: object) -> object:  # noqa: ARG001
            if "exec-out screencap -p" in command:
                return types.SimpleNamespace(returncode=1, stdout=b"", stderr=b"device not found")
            if "shell screencap -p" in command:
                return types.SimpleNamespace(returncode=1, stdout=b"", stderr=b"device not found")
            if "get-state" in command:
                return types.SimpleNamespace(returncode=1, stdout="", stderr="error: device not found")
            if "shell getprop sys.boot_completed" in command:
                return types.SimpleNamespace(returncode=1, stdout="", stderr="device not found")
            if "shell wm size" in command:
                return types.SimpleNamespace(returncode=1, stdout="", stderr="device not found")
            return types.SimpleNamespace(returncode=1, stdout=b"", stderr=b"device not found")

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "snowl_mobile.adapters.agents.mobile_agent_e_runner.subprocess.run",
            side_effect=fake_run,
        ), patch(
            "snowl_mobile.adapters.agents.mobile_agent_e_runner._dump_ui_hierarchy_xml",
            return_value=None,
        ), patch(
            "snowl_mobile.adapters.agents.mobile_agent_e_runner.time.sleep",
            return_value=None,
        ):
            screenshot_path = Path(temp_dir) / "screenshot" / "screenshot.png"
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            screenshot_path.write_bytes(png_bytes)

            with self.assertRaises(RuntimeError) as context:
                mobile_agent_e_runner._capture_screenshot_with_fallback(  # noqa: SLF001
                    types.SimpleNamespace(SCREENSHOT_DIR=str(screenshot_path.parent)),
                    "adb -s emulator-5554",
                    screenshot_path=screenshot_path,
                )

        self.assertIn("device not found", str(context.exception))

    def test_image_encoding_normalizes_bad_current_screenshot_from_last_valid_image(self) -> None:
        try:
            from PIL import Image
        except ModuleNotFoundError:
            self.skipTest("Pillow is not installed in this test interpreter")

        with tempfile.TemporaryDirectory() as temp_dir:
            screenshot_dir = Path(temp_dir) / "screenshot"
            screenshot_dir.mkdir()
            empty_current = screenshot_dir / "screenshot.png"
            empty_current.write_bytes(b"")
            last_valid = screenshot_dir / "last_screenshot.png"
            Image.new("RGB", (4, 4), color="red").save(last_valid, "PNG")

            fake_api = types.ModuleType("MobileAgentE.api")
            fake_api.encode_image = lambda image_path: "old"  # noqa: ARG005
            fake_agents = types.ModuleType("MobileAgentE.agents")
            fake_agents.encode_image = lambda image_path: "old"  # noqa: ARG005
            upstream_module = types.SimpleNamespace()

            with patch.dict(
                sys.modules,
                {
                    "MobileAgentE.api": fake_api,
                    "MobileAgentE.agents": fake_agents,
                },
                clear=False,
            ):
                mobile_agent_e_runner._patch_image_encoding(upstream_module)  # noqa: SLF001
                encoded = fake_agents.encode_image(str(empty_current))

        decoded = base64.b64decode(encoded)
        with Image.open(io.BytesIO(decoded)) as image:
            self.assertEqual(image.format, "PNG")
            self.assertEqual(image.size, (4, 4))

    def test_image_chat_payloads_use_png_data_urls(self) -> None:
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "screen.png"
            image_path.write_bytes(png_bytes)
            fake_agents = types.ModuleType("MobileAgentE.agents")
            fake_chat = types.ModuleType("MobileAgentE.chat")
            upstream_module = types.SimpleNamespace()

            with patch.dict(
                sys.modules,
                {
                    "MobileAgentE.agents": fake_agents,
                    "MobileAgentE.chat": fake_chat,
                },
                clear=False,
            ):
                mobile_agent_e_runner._patch_image_chat_payloads(upstream_module)  # noqa: SLF001
                history = fake_agents.add_response("user", "look", [], image=str(image_path))

        image_url = history[0][1][1]["image_url"]["url"]
        self.assertTrue(image_url.startswith("data:image/png;base64,"))
        self.assertNotIn("image/jpeg", image_url)

    def test_lightweight_perception_installs_callable_ocr_shims(self) -> None:
        fake_text_localization = types.ModuleType("MobileAgentE.text_localization")
        fake_text_localization.ocr = lambda *_args, **_kwargs: (["old"], [[1, 2, 3, 4]])
        fake_agents = types.ModuleType("MobileAgentE.agents")
        fake_agents.ocr = lambda *_args, **_kwargs: (["old"], [[1, 2, 3, 4]])
        upstream_module = types.SimpleNamespace(SCREENSHOT_DIR="screenshot")

        with patch.dict(
            sys.modules,
            {
                "MobileAgentE.text_localization": fake_text_localization,
                "MobileAgentE.agents": fake_agents,
            },
            clear=False,
        ):
            mobile_agent_e_runner._enable_lightweight_perception(upstream_module)  # noqa: SLF001

        perceptor = upstream_module.Perceptor("adb")
        self.assertTrue(callable(perceptor.ocr_detection))
        self.assertTrue(callable(perceptor.ocr_recognition))
        self.assertEqual(perceptor.ocr_detection(object())["polygons"].shape[0], 0)
        self.assertEqual(perceptor.ocr_recognition(object()), {"text": [""]})
        self.assertEqual(fake_text_localization.ocr("screen.png", None, None), ([], []))
        self.assertEqual(fake_agents.ocr("screen.png", None, None), ([], []))

    def test_lightweight_perception_perceptor_returns_fallback_observation(self) -> None:
        fake_text_localization = types.ModuleType("MobileAgentE.text_localization")
        fake_agents = types.ModuleType("MobileAgentE.agents")
        upstream_module = types.SimpleNamespace(SCREENSHOT_DIR="screenshot")

        with patch.dict(
            sys.modules,
            {
                "MobileAgentE.text_localization": fake_text_localization,
                "MobileAgentE.agents": fake_agents,
            },
            clear=False,
        ):
            mobile_agent_e_runner._enable_lightweight_perception(upstream_module)  # noqa: SLF001

        perceptor = upstream_module.Perceptor("adb")
        screenshot_path = ROOT / "tmp" / "mobile-agent-e-runner-test" / "screen.png"
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        with patch(
            "snowl_mobile.adapters.agents.mobile_agent_e_runner._capture_screenshot_with_fallback",
            return_value=screenshot_path,
        ), patch(
            "snowl_mobile.adapters.agents.mobile_agent_e_runner._read_device_dimensions",
            return_value=(1080, 2400),
        ):
            perception_infos, width, height = perceptor.get_perception_infos(str(screenshot_path))

        self.assertEqual((width, height), (1080, 2400))
        self.assertEqual(
            perception_infos,
            [
                {
                    "text": "text: lightweight perception fallback active",
                    "coordinates": [540, 1200],
                }
            ],
        )

    def test_reasoning_error_guard_mentions_diagnostics_path(self) -> None:
        diagnostics_path = ROOT / "tmp" / "mobile-agent-e-runner-test" / "reasoning.json"
        upstream_module = types.SimpleNamespace(
            BACKBONE_TYPE="OpenAI",
            OPENAI_API_URL="https://api.example.com/v1/chat/completions",
            REASONING_MODEL="demo-model",
            get_reasoning_model_api_response=lambda *args, **kwargs: None,
        )

        mobile_agent_e_runner._patch_reasoning_error_guard(  # noqa: SLF001
            upstream_module,
            diagnostics_path=diagnostics_path,
        )

        with self.assertRaises(RuntimeError) as context:
            upstream_module.get_reasoning_model_api_response([["user", [{"type": "text", "text": "hi"}]]])

        self.assertIn(str(diagnostics_path), str(context.exception))
        self.assertIn("api.example.com", str(context.exception))
        self.assertIn("demo-model", str(context.exception))

    def test_reasoning_client_writes_diagnostics_for_http_failures(self) -> None:
        fake_api = types.ModuleType("MobileAgentE.api")
        fake_api.inference_chat = lambda *args, **kwargs: None
        fake_api.track_usage = lambda res_json, api_key: {"model": "demo", "usage": {}}  # noqa: ARG005
        fake_api.sleep = lambda seconds: None  # noqa: ARG005
        upstream_module = types.SimpleNamespace(BACKBONE_TYPE="Gemini")

        class _FakeResponse:
            status_code = 500
            text = "upstream exploded"

            @staticmethod
            def json() -> dict[str, object]:
                return {"error": {"message": "boom"}}

        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            sys.modules,
            {"MobileAgentE.api": fake_api},
            clear=False,
        ), patch("requests.post", return_value=_FakeResponse()):
            diagnostics_path = Path(temp_dir) / "reasoning_request_diagnostics.json"
            mobile_agent_e_runner._patch_reasoning_client(  # noqa: SLF001
                upstream_module,
                diagnostics_path=diagnostics_path,
            )

            result = upstream_module.inference_chat(
                [["user", [{"type": "text", "text": "hello"}]]],
                "demo-model",
                "https://api.example.com/v1/chat/completions",
                "demo-token",
            )

            self.assertIsNone(result)
            diagnostics_payload = json.loads(diagnostics_path.read_text(encoding="utf-8"))
            self.assertEqual(diagnostics_payload["transport"], "requests")
            self.assertEqual(diagnostics_payload["api_url"], "https://api.example.com/v1/chat/completions")
            self.assertEqual(diagnostics_payload["attempts"][-1]["status_code"], 500)
            self.assertIn("upstream exploded", diagnostics_payload["attempts"][-1]["response_text_preview"])

    def test_reasoning_client_can_use_openai_sdk_fallback(self) -> None:
        fake_api = types.ModuleType("MobileAgentE.api")
        fake_api.inference_chat = lambda *args, **kwargs: None
        fake_api.track_usage = lambda res_json, api_key: {"model": "demo", "usage": {}}  # noqa: ARG005
        fake_api.sleep = lambda seconds: None  # noqa: ARG005
        upstream_module = types.SimpleNamespace(BACKBONE_TYPE="OpenAI")
        captured_client_config: dict[str, object] = {}

        class _FakeResponse:
            choices = [types.SimpleNamespace(message=types.SimpleNamespace(content="sdk-response"))]

        class _FakeCompletions:
            @staticmethod
            def create(**kwargs) -> _FakeResponse:  # type: ignore[name-defined]
                return _FakeResponse()

        class _FakeChat:
            completions = _FakeCompletions()

        class _FakeClient:
            def __init__(self, *, base_url: str, api_key: str, timeout: float) -> None:
                captured_client_config["base_url"] = base_url
                captured_client_config["api_key"] = api_key
                captured_client_config["timeout"] = timeout
                self.chat = _FakeChat()

        fake_openai = types.ModuleType("openai")
        fake_openai.OpenAI = _FakeClient

        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            sys.modules,
            {
                "MobileAgentE.api": fake_api,
                "openai": fake_openai,
            },
            clear=False,
        ):
            diagnostics_path = Path(temp_dir) / "reasoning_request_diagnostics.json"
            mobile_agent_e_runner._patch_reasoning_client(  # noqa: SLF001
                upstream_module,
                diagnostics_path=diagnostics_path,
            )

            result = upstream_module.inference_chat(
                [["user", [{"type": "text", "text": "hello"}]]],
                "demo-model",
                "https://api.example.com/v1/chat/completions",
                "demo-token",
            )

            self.assertEqual(result, "sdk-response")
            self.assertEqual(captured_client_config["base_url"], "https://api.example.com/v1")
            self.assertEqual(captured_client_config["api_key"], "demo-token")
            self.assertFalse(diagnostics_path.exists())

    def test_recover_jsonish_object_handles_code_fence_payload(self) -> None:
        payload = """
### Action ###
```json
{"name": "Tap", "arguments": {"x": 540, "y": 2270}}
```
        """

        parsed = mobile_agent_e_runner._recover_jsonish_object(payload)  # noqa: SLF001

        self.assertEqual(
            parsed,
            {"name": "Tap", "arguments": {"x": 540, "y": 2270}},
        )

    def test_recover_mobile_agent_e_action_object_fills_missing_coordinate_key(self) -> None:
        fake_agents_module = types.SimpleNamespace(
            ATOMIC_ACTION_SIGNITURES={
                "Tap": {
                    "arguments": ["x", "y"],
                }
            },
            INIT_SHORTCUTS={},
        )

        parsed = mobile_agent_e_runner._recover_mobile_agent_e_action_object(  # noqa: SLF001
            '{"name":"Tap", "arguments":{"x":927, 1976}}',
            agents_module=fake_agents_module,
        )

        self.assertEqual(
            parsed,
            {"name": "Tap", "arguments": {"x": 927, "y": 1976}},
        )

    def test_normalize_mobile_agent_e_action_object_splits_packed_tap_coordinates(self) -> None:
        parsed = mobile_agent_e_runner._normalize_mobile_agent_e_action_object(  # noqa: SLF001
            {"name": "Tap", "arguments": {"x": [680, 480]}}
        )

        self.assertEqual(
            parsed,
            {"name": "Tap", "arguments": {"x": 680, "y": 480}},
        )

    def test_normalize_mobile_agent_e_action_object_flattens_swipe_coordinate_quad(self) -> None:
        parsed = mobile_agent_e_runner._normalize_mobile_agent_e_action_object(  # noqa: SLF001
            {"name": "Swipe", "arguments": {"x1": [540, 1200, 540, 240]}}
        )

        self.assertEqual(
            parsed,
            {
                "name": "Swipe",
                "arguments": {"x1": 540, "y1": 1200, "x2": 540, "y2": 240},
            },
        )

    def test_normalize_mobile_agent_e_shortcut_preserves_numeric_looking_text(self) -> None:
        parsed = mobile_agent_e_runner._normalize_mobile_agent_e_action_object(  # noqa: SLF001
            {
                "name": "Tap_Type_and_Enter",
                "arguments": {"x": "540", "y": "930", "text": "+13920741751"},
            }
        )

        self.assertEqual(
            parsed,
            {
                "name": "Tap_Type_and_Enter",
                "arguments": {"x": 540, "y": 930, "text": "+13920741751"},
            },
        )

    def test_normalize_mobile_agent_e_type_converts_json_number_to_text(self) -> None:
        parsed = mobile_agent_e_runner._normalize_mobile_agent_e_action_object(  # noqa: SLF001
            {"name": "Type", "arguments": {"text": 67.41}}
        )

        self.assertEqual(parsed, {"name": "Type", "arguments": {"text": "67.41"}})

    def test_validate_mobile_agent_e_atomic_arguments_rejects_non_numeric_tap_coordinate(self) -> None:
        error_message = mobile_agent_e_runner._validate_mobile_agent_e_atomic_arguments(  # noqa: SLF001
            "Tap",
            {"x": "x", "y": 540},
        )

        self.assertEqual(
            error_message,
            "Mobile-Agent-E atomic action 'Tap' has non-numeric coordinates for: x.",
        )

    def test_patch_operator_action_argument_guard_normalizes_before_execution(self) -> None:
        recorded: list[tuple[str, object]] = []

        class FakeOperator:
            def execute_atomic_action(self, action: str, arguments: dict | None, **kwargs: object) -> None:  # noqa: ARG002
                recorded.append((action, arguments))

        fake_agents_module = types.ModuleType("MobileAgentE.agents")
        fake_agents_module.Operator = FakeOperator

        with patch.dict(
            sys.modules,
            {"MobileAgentE.agents": fake_agents_module},
            clear=False,
        ):
            mobile_agent_e_runner._patch_operator_action_argument_guard()  # noqa: SLF001
            fake_agents_module.Operator().execute_atomic_action(
                "Tap",
                {"x": [680, 480]},
            )

        self.assertEqual(recorded, [("Tap", {"x": 680, "y": 480})])

    def test_patch_operator_action_argument_guard_is_idempotent(self) -> None:
        class FakeOperator:
            def execute_atomic_action(self, action: str, arguments: dict | None, **kwargs: object) -> None:  # noqa: ARG002
                return None

        fake_agents_module = types.ModuleType("MobileAgentE.agents")
        fake_agents_module.Operator = FakeOperator

        with patch.dict(
            sys.modules,
            {"MobileAgentE.agents": fake_agents_module},
            clear=False,
        ):
            mobile_agent_e_runner._patch_operator_action_argument_guard()  # noqa: SLF001
            first_wrapper = fake_agents_module.Operator.execute_atomic_action
            mobile_agent_e_runner._patch_operator_action_argument_guard()  # noqa: SLF001
            second_wrapper = fake_agents_module.Operator.execute_atomic_action

        self.assertIs(first_wrapper, second_wrapper)

    def test_patch_operator_execute_guard_returns_failed_atomic_action_for_invalid_arguments(self) -> None:
        recorded_calls: list[tuple[str, object]] = []

        class FakeOperator:
            adb = "adb"

            def execute(self, action_str: str, info_pool: object, screenshot_log_dir=None, iter: str = "", **kwargs: object):  # noqa: ANN001, ARG002
                action_object = fake_agents_module.extract_json_object(action_str)
                action = action_object["name"]
                arguments = action_object["arguments"]
                recorded_calls.append((action, arguments))
                self.execute_atomic_action(action, arguments, info_pool=info_pool, **kwargs)
                return action_object, 1, None

            def execute_atomic_action(self, action: str, arguments: dict | None, **kwargs: object) -> None:  # noqa: ARG002
                recorded_calls.append((action, arguments))
                raise AssertionError("execute_atomic_action should not be called for invalid coordinates")

        fake_agents_module = types.ModuleType("MobileAgentE.agents")
        fake_agents_module.Operator = FakeOperator
        fake_agents_module.ATOMIC_ACTION_SIGNITURES = {"Tap": {"arguments": ["x", "y"]}}
        fake_agents_module.extract_json_object = lambda _text, json_type="dict": {  # noqa: ARG005
            "name": "Tap",
            "arguments": {"x": "x", "y": 540},
        }

        with patch.dict(
            sys.modules,
            {"MobileAgentE.agents": fake_agents_module},
            clear=False,
        ):
            mobile_agent_e_runner._patch_operator_execute_guard()  # noqa: SLF001
            info_pool = types.SimpleNamespace(shortcuts={})
            action_object, num_atomic_actions_executed, error_message = fake_agents_module.Operator().execute(
                "ignored",
                info_pool,
            )

        self.assertEqual(
            action_object,
            {"name": "Tap", "arguments": {"x": "x", "y": 540}},
        )
        self.assertEqual(num_atomic_actions_executed, 0)
        self.assertEqual(
            error_message,
            "Mobile-Agent-E atomic action 'Tap' has non-numeric coordinates for: x.",
        )
        self.assertEqual(recorded_calls, [])

    def test_patch_operator_execute_guard_returns_failed_shortcut_for_invalid_substep(self) -> None:
        recorded_calls: list[tuple[str, object]] = []

        class FakeOperator:
            adb = "adb"

            def execute(self, action_str: str, info_pool: object, screenshot_log_dir=None, iter: str = "", **kwargs: object):  # noqa: ANN001, ARG002
                action_object = fake_agents_module.extract_json_object(action_str)
                action = action_object["name"]
                arguments = action_object["arguments"]
                shortcut = info_pool.shortcuts[action]
                for atomic_action in shortcut["atomic_action_sequence"]:
                    atomic_action_name = atomic_action["name"]
                    atomic_action_args = {
                        key: arguments.get(value, value)
                        for key, value in atomic_action["arguments_map"].items()
                    }
                    recorded_calls.append((atomic_action_name, atomic_action_args))
                    self.execute_atomic_action(atomic_action_name, atomic_action_args, info_pool=info_pool, **kwargs)
                return action_object, len(shortcut["atomic_action_sequence"]), None

            def execute_atomic_action(self, action: str, arguments: dict | None, **kwargs: object) -> None:  # noqa: ARG002
                recorded_calls.append((action, arguments))
                raise AssertionError("execute_atomic_action should not be called for invalid shortcut coordinates")

        fake_agents_module = types.ModuleType("MobileAgentE.agents")
        fake_agents_module.Operator = FakeOperator
        fake_agents_module.ATOMIC_ACTION_SIGNITURES = {
            "Tap": {"arguments": ["x", "y"]},
            "Type": {"arguments": ["text"]},
            "Enter": {"arguments": []},
        }
        fake_agents_module.extract_json_object = lambda _text, json_type="dict": {  # noqa: ARG005
            "name": "Tap_Type_and_Enter",
            "arguments": {"x": "x", "y": 540, "text": "hello"},
        }

        with patch.dict(
            sys.modules,
            {"MobileAgentE.agents": fake_agents_module},
            clear=False,
        ):
            mobile_agent_e_runner._patch_operator_execute_guard()  # noqa: SLF001
            info_pool = types.SimpleNamespace(
                shortcuts={
                    "Tap_Type_and_Enter": {
                        "atomic_action_sequence": [
                            {"name": "Tap", "arguments_map": {"x": "x", "y": "y"}},
                            {"name": "Type", "arguments_map": {"text": "text"}},
                            {"name": "Enter", "arguments_map": {}},
                        ]
                    }
                }
            )
            action_object, num_atomic_actions_executed, error_message = fake_agents_module.Operator().execute(
                "ignored",
                info_pool,
            )

        self.assertEqual(
            action_object,
            {"name": "Tap_Type_and_Enter", "arguments": {"x": "x", "y": 540, "text": "hello"}},
        )
        self.assertEqual(num_atomic_actions_executed, 0)
        self.assertIn("Mobile-Agent-E atomic action 'Tap' has non-numeric coordinates for: x.", error_message)
        self.assertIn("Error in executing step 0: Tap", error_message)
        self.assertEqual(recorded_calls, [])

    def test_patch_operator_execute_guard_re_raises_non_argument_runtime_errors(self) -> None:
        class FakeOperator:
            adb = "adb"

            def execute(self, action_str: str, info_pool: object, screenshot_log_dir=None, iter: str = "", **kwargs: object):  # noqa: ANN001, ARG002
                action_object = fake_agents_module.extract_json_object(action_str)
                action = action_object["name"]
                arguments = action_object["arguments"]
                self.execute_atomic_action(action, arguments, info_pool=info_pool, **kwargs)
                return action_object, 1, None

            def execute_atomic_action(self, action: str, arguments: dict | None, **kwargs: object) -> None:  # noqa: ARG002
                raise RuntimeError("adb disconnected")

        fake_agents_module = types.ModuleType("MobileAgentE.agents")
        fake_agents_module.Operator = FakeOperator
        fake_agents_module.ATOMIC_ACTION_SIGNITURES = {"Tap": {"arguments": ["x", "y"]}}
        fake_agents_module.extract_json_object = lambda _text, json_type="dict": {  # noqa: ARG005
            "name": "Tap",
            "arguments": {"x": 320, "y": 540},
        }

        with patch.dict(
            sys.modules,
            {"MobileAgentE.agents": fake_agents_module},
            clear=False,
        ):
            mobile_agent_e_runner._patch_operator_execute_guard()  # noqa: SLF001
            info_pool = types.SimpleNamespace(shortcuts={})
            with self.assertRaisesRegex(RuntimeError, "adb disconnected"):
                fake_agents_module.Operator().execute("ignored", info_pool)


if __name__ == "__main__":
    unittest.main()
