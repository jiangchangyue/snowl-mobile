from __future__ import annotations

import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from snowl_mobile.adapters.agents.open_autoglm import (
    OpenAutoGLMAgentAdapter,
    OpenAutoGLMRawOutput,
    build_open_autoglm_report,
)
from snowl_mobile.adapters.benchmarks.mobilesafetybench import MobileSafetyBenchBenchmarkAdapter
from snowl_mobile.adapters.builtin import create_builtin_registry
from snowl_mobile.core.compatibility import CompatibilityResolver
from snowl_mobile.core.config_loader import load_project_spec
from snowl_mobile.core.run_context import RunContext
from snowl_mobile.core.states import TrialStatus
from snowl_mobile.core.trial_context import TrialContext
from snowl_mobile.core.trial_spec import TrialSpec
from snowl_mobile.integration.agent_inspector import AgentRepositoryInspector


OPEN_AUTOGLM_REPO = ROOT / "references" / "agents" / "Open-AutoGLM"
OPEN_AUTOGLM_CONFIG = ROOT / "configs" / "runs" / "autoglm_mobilesafetybench.yml"


class OpenAutoGLMAdapterTestCase(unittest.TestCase):
    def test_builtin_registry_registers_open_autoglm_adapter(self) -> None:
        registry = create_builtin_registry()

        entry = registry.resolve_agent("open_autoglm")

        self.assertEqual(entry.adapter_id, "open_autoglm")
        self.assertEqual(entry.metadata.integration_mode, "hybrid")
        self.assertIn("OPEN_AUTOGLM_HOME", entry.metadata.required_env)
        self.assertIn("adb_appium", entry.metadata.supported_backends)
        self.assertIn("mobilesafetybench", entry.metadata.supported_benchmarks)

    def test_repo_inspection_reports_real_agent_structure(self) -> None:
        inspection = AgentRepositoryInspector().inspect(OPEN_AUTOGLM_REPO)

        self.assertEqual(inspection.repo_name, "Open-AutoGLM")
        self.assertEqual(inspection.suggested_integration_mode, "hybrid")
        self.assertIn("phone_agent/model/client.py", inspection.model_entrypoints)
        self.assertIn("phone_agent/device_factory.py", inspection.device_control_candidates)
        self.assertIn("phone_agent/actions/handler.py", inspection.action_normalization_candidates)
        self.assertIn("image", inspection.observation_modalities)
        self.assertIn("adb", inspection.tool_backends)
        self.assertIn("hdc", inspection.tool_backends)
        self.assertIn("ios_wda", inspection.tool_backends)
        self.assertIn("phone_agent/actions/handler.py", inspection.human_confirmation_candidates)
        self.assertIn("phone_agent/model/client.py", inspection.raw_output_capture_points)

    def test_open_autoglm_compatibility_is_vision_and_backend_aware(self) -> None:
        spec = load_project_spec(OPEN_AUTOGLM_CONFIG)
        agent = spec.agents[0]
        benchmark = spec.benchmarks[0]
        model = spec.models[0]
        runtime_recipe = spec.build_runtime_recipe(agent, benchmark)
        resolver = CompatibilityResolver(registry=create_builtin_registry())

        model_report = resolver.check_agent_model(agent, model)
        runtime_report = resolver.check_agent_runtime(agent, runtime_recipe)
        incompatible_model = replace(
            model,
            modalities=("text",),
            supports_image_input=False,
        )
        incompatible_runtime = replace(
            runtime_recipe,
            control_backend="grpc",
            backend_requirements=("grpc",),
        )

        self.assertTrue(model_report.compatible)
        self.assertTrue(runtime_report.compatible)
        self.assertFalse(resolver.check_agent_model(agent, incompatible_model).compatible)
        self.assertIn(
            "missing required modalities: image",
            resolver.check_agent_model(agent, incompatible_model).render(),
        )
        self.assertFalse(resolver.check_agent_runtime(agent, incompatible_runtime).compatible)
        self.assertIn(
            "supported_backends",
            resolver.check_agent_runtime(agent, incompatible_runtime).render(),
        )

    def test_normalize_action_handles_open_autoglm_pseudocode(self) -> None:
        adapter = OpenAutoGLMAgentAdapter()
        raw_output = OpenAutoGLMRawOutput(
            thinking="I should tap the confirm button.",
            action_text='do(action="Tap", element=[512,820], message="important operation")',
            raw_content='I should tap the confirm button.\ndo(action="Tap", element=[512,820], message="important operation")',
            time_to_first_token_ms=50,
            time_to_thinking_end_ms=150,
            total_time_ms=210,
        )

        record = adapter.normalize_action(raw_output)

        self.assertEqual(record.parsed_action["_metadata"], "do")
        self.assertEqual(record.parsed_action["action"], "Tap")
        self.assertEqual(record.executed_action["normalized_action"], "tap")
        self.assertTrue(record.executed_action["requires_confirmation"])
        self.assertEqual(record.executed_action["coordinate_space"], "relative_0_1000")

    def test_normalize_action_strips_answer_wrappers_from_real_response(self) -> None:
        adapter = OpenAutoGLMAgentAdapter()
        raw_output = OpenAutoGLMRawOutput(
            thinking="<think>\nNeed to open Messages.\n</think>\n<answer>",
            action_text='do(action="Tap", element=[418, 1975])\n</answer>',
            raw_content=(
                "<think>\nNeed to open Messages.\n</think>\n<answer>\n"
                'do(action="Tap", element=[418, 1975])\n'
                "</answer>"
            ),
            time_to_first_token_ms=1001,
            time_to_thinking_end_ms=1825,
            total_time_ms=2239,
        )

        record = adapter.normalize_action(raw_output)

        self.assertEqual(record.parsed_action["_metadata"], "do")
        self.assertEqual(record.parsed_action["action"], "Tap")
        self.assertEqual(record.parsed_action["element"], [418, 1975])
        self.assertEqual(record.executed_action["normalized_action"], "tap")

    def test_mock_run_writes_raw_outputs_and_action_record(self) -> None:
        adapter = OpenAutoGLMAgentAdapter()
        benchmark_adapter = MobileSafetyBenchBenchmarkAdapter()
        report = build_open_autoglm_report()
        spec = load_project_spec(OPEN_AUTOGLM_CONFIG)
        run_context = RunContext(
            run_id="open-autoglm-test-run",
            project_snapshot=spec,
            artifact_root=ROOT / "runs" / "open-autoglm-test-run",
        )
        benchmark = spec.benchmarks[0]
        agent = spec.agents[0]
        task_payload = benchmark_adapter.list_tasks(run_context)[0]
        trial_spec = TrialSpec(
            trial_id="open-autoglm-trial-001",
            run_id="open-autoglm-test-run",
            benchmark_id=benchmark.benchmark_id,
            task_id=str(task_payload["task_id"]),
            agent_id=agent.agent_id,
            agent_variant=agent.variant,
            model_id=agent.model_ref,
            seed="seed-0001",
            status=TrialStatus.PENDING,
            artifact_level=spec.artifacts.level,
            runtime_recipe=spec.build_runtime_recipe(agent, benchmark),
            timeout_sec=spec.runtime.timeout_sec,
            max_steps=spec.runtime.max_steps,
        )
        ctx = TrialContext(trial_spec=trial_spec)

        benchmark_adapter.prepare_trial(ctx)
        benchmark_adapter.seed_environment(ctx)
        initial_observation = benchmark_adapter.get_initial_observation(ctx)

        with tempfile.TemporaryDirectory() as temp_dir:
            request = adapter.build_run_request(
                ctx,
                output_dir=Path(temp_dir),
                observation=initial_observation,
                task_instruction=str(task_payload["instruction"]),
                mock_mode=True,
            )
            result = adapter.run_wrapped_agent(request)

            self.assertEqual(result.action_record.parsed_action["_metadata"], "finish")
            self.assertTrue(result.platform_metrics["finished"])
            self.assertTrue(Path(result.raw_artifacts["raw_text_path"]).exists())
            self.assertTrue(Path(result.raw_artifacts["raw_json_path"]).exists())
            self.assertTrue(Path(result.raw_artifacts["action_record_path"]).exists())
            self.assertTrue(Path(result.raw_artifacts["model_binding_path"]).exists())
            self.assertEqual(result.model_binding.api_style, "openai_chat")
            self.assertEqual(report.recommended_integration_mode, "hybrid")


if __name__ == "__main__":
    unittest.main()
