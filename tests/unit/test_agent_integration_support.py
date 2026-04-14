from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from snowl_mobile.integration.agent_contract import AgentCapabilityDeclaration
from snowl_mobile.integration.agent_inspector import AgentRepositoryInspector
from snowl_mobile.integration.agent_scaffold import (
    AgentPackageScaffoldGenerator,
    AgentPackageScaffoldRequest,
)
from snowl_mobile.models.model_spec import ModelSpec


AGENT_REPO = ROOT / "references" / "agents" / "mock-agent-repo"


class AgentIntegrationSupportTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.inspector = AgentRepositoryInspector()

    def test_mock_agent_repo_inspection_is_structured(self) -> None:
        inspection = self.inspector.inspect(AGENT_REPO)

        self.assertEqual(inspection.repo_name, "mock-agent-repo")
        self.assertIn("examples", inspection.examples_dirs)
        self.assertIn("mock_agent/model_client.py", inspection.model_entrypoints)
        self.assertIn("mock_agent/device_controller.py", inspection.device_control_candidates)
        self.assertIn("mock_agent/action_parser.py", inspection.action_normalization_candidates)
        self.assertIn("image", inspection.observation_modalities)
        self.assertIn("json_action", inspection.action_output_forms)
        self.assertIn("adb", inspection.tool_backends)
        self.assertIn("appium", inspection.tool_backends)
        self.assertIn("mock_agent/confirmation_gate.py", inspection.human_confirmation_candidates)
        self.assertIn("mock_agent/raw_capture.py", inspection.raw_output_capture_points)

    def test_agent_scaffold_generator_writes_text_and_vision_packages(self) -> None:
        inspection = self.inspector.inspect(AGENT_REPO)
        generator = AgentPackageScaffoldGenerator()
        with tempfile.TemporaryDirectory() as temp_dir:
            text_result = generator.generate(
                AgentPackageScaffoldRequest(
                    adapter_id="mock_text_agent",
                    inspection=inspection,
                    output_dir=Path(temp_dir),
                    integration_mode="hybrid",
                    capability_profile="text-only",
                )
            )
            vision_result = generator.generate(
                AgentPackageScaffoldRequest(
                    adapter_id="mock_vision_agent",
                    inspection=inspection,
                    output_dir=Path(temp_dir),
                    integration_mode="hybrid",
                    capability_profile="vision-capable",
                )
            )

            self.assertTrue((text_result.scaffold_root / "adapter.py").exists())
            self.assertTrue((text_result.scaffold_root / "register.py").exists())
            self.assertTrue((text_result.scaffold_root / "capability.json").exists())
            self.assertTrue((text_result.scaffold_root / "config.example.yml").exists())
            self.assertTrue((text_result.scaffold_root / "README.md").exists())
            self.assertTrue(
                (text_result.scaffold_root / "tests" / "test_mock_text_agent_integration.py").exists()
            )

            text_capability = json.loads(
                (text_result.scaffold_root / "capability.json").read_text(encoding="utf-8")
            )
            vision_capability = json.loads(
                (vision_result.scaffold_root / "capability.json").read_text(encoding="utf-8")
            )
            contract_payload = json.loads(
                (vision_result.scaffold_root / "contract.json").read_text(encoding="utf-8")
            )
            self.assertEqual(text_capability["input_modalities"], ["text"])
            self.assertEqual(vision_capability["input_modalities"], ["text", "image"])
            self.assertTrue(vision_capability["supports_image_input"])
            self.assertEqual(contract_payload["model_call_entry"], "mock_agent/model_client.py")
            self.assertEqual(contract_payload["action_normalization_entry"], "mock_agent/action_parser.py")

    def test_capability_declaration_reports_model_compatibility(self) -> None:
        capability = AgentCapabilityDeclaration(
            input_modalities=("text", "image"),
            action_output_schema="json_action",
            supported_model_protocols=("openai_chat",),
            tool_backends=("adb",),
            runtime_requirements=("pillow>=10.0",),
            human_confirmation_mode="none",
            raw_output_capture_points=("mock_agent/raw_capture.py",),
            supports_image_input=True,
            supports_tool_calling=False,
            supports_json_mode=True,
            requires_tool_calling=False,
            requires_json_mode=False,
        )
        compatible_model = ModelSpec(
            model_id="dummy_vision_model",
            provider="openai",
            api_style="openai_chat",
            modalities=("text", "image"),
            supports_image_input=True,
            supports_tool_calling=False,
            supports_json_mode=True,
        )
        incompatible_model = ModelSpec(
            model_id="dummy_text_model",
            provider="openai",
            api_style="openai_chat",
            modalities=("text",),
            supports_image_input=False,
            supports_tool_calling=False,
            supports_json_mode=True,
        )

        self.assertEqual(capability.compatibility_issues(compatible_model), [])
        issues = capability.compatibility_issues(incompatible_model)
        self.assertIn("model is missing required modalities: image", issues)
        self.assertIn("model does not support image input", issues)
