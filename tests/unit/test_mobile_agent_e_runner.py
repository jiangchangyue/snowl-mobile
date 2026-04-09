from __future__ import annotations

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
            screenshot_path = Path(temp_dir) / "screenshot.jpg"
            xml_path = screenshot_path.with_suffix(".xml")
            screenshot_path.write_bytes(b"jpg")
            xml_path.write_text("<hierarchy />\n", encoding="utf-8")

            mobile_agent_e_runner._copy_xml_sidecar_if_present(  # noqa: SLF001
                screenshot_path,
                screenshot_path,
            )

            self.assertEqual(xml_path.read_text(encoding="utf-8"), "<hierarchy />\n")

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
        self.assertEqual(fake_text_localization.ocr("screen.jpg", None, None), ([], []))
        self.assertEqual(fake_agents.ocr("screen.jpg", None, None), ([], []))

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
        screenshot_path = ROOT / "tmp" / "mobile-agent-e-runner-test" / "screen.jpg"
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


if __name__ == "__main__":
    unittest.main()
