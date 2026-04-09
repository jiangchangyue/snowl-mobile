from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from snowl_mobile.core.config_loader import load_project_spec


class ConfigLoaderTestCase(unittest.TestCase):
    def test_project_example_loads(self) -> None:
        spec = load_project_spec(ROOT / "project.example.yml")
        self.assertEqual(spec.project.name, "snowl-mobile-demo")
        self.assertEqual(spec.runtime.batch_size, 2)
        self.assertEqual(len(spec.expand_matrix()), 2)
        self.assertEqual(spec.agents[0].supported_model_protocols, ("openai_chat",))
        self.assertEqual(spec.benchmarks[0].scorer_ref, "dummy.native")
        self.assertEqual(spec.devices.default_profile, "api34_base")
        self.assertEqual(spec.reset.name, "snapshot_then_seed")
        self.assertEqual(spec.artifacts.level.value, "standard")
        self.assertEqual(len(spec.models), 2)
        self.assertEqual(len(spec.agents), 2)
        self.assertEqual(len(spec.pair_runtime_recipes), 1)
        self.assertEqual(spec.pair_runtime_recipes[0].bridge_id, "dummy_vision__dummy_benchmark")
        self.assertEqual(spec.devices.device_mode.value, "fake")

    def test_project_summary_is_normalized(self) -> None:
        spec = load_project_spec(ROOT / "project.example.yml")
        summary = spec.normalized_summary()
        self.assertEqual(summary["matrix"]["trial_blueprints"], 2)
        self.assertEqual(summary["matrix"]["pair_runtime_recipe_count"], 1)
        self.assertEqual(summary["runtime"]["default_worker_mode"], "venv")
        self.assertEqual(summary["policies"]["artifact_level"], "standard")
        self.assertEqual(summary["agents"][0]["agent_id"], "dummy_text_agent")
        self.assertEqual(summary["devices"]["device_mode"], "fake")

    def test_device_settings_support_string_aliases_for_existing_device_mode(self) -> None:
        config_yaml = """
project:
  name: device-demo
  run_name: device-run
models:
  - id: dummy_text_model
    provider: openai
    api_style: openai_chat
    modalities: [text]
    supports_image_input: false
    supports_tool_calling: false
    supports_json_mode: false
agents:
  - id: dummy_text_agent
    variant: default
    model_ref: dummy_text_model
    integration_mode: native
    required_modalities: [text]
    supported_modalities: [text]
    supported_model_protocols: [openai_chat]
    supports_tool_calling: false
    supports_image_input: false
    supports_json_mode: false
    requires_tool_calling: false
    requires_json_mode: false
    required_env: []
    action_schema: dummy_text_action_v1
    prompt_contract_version: dummy.v1
benchmarks:
  - id: dummy_benchmark
    integration_mode: wrap
    task_source:
      kind: inline
      selector: default
    metric_schema:
      primary: task_success
      native: [task_success]
    scorer_ref: dummy.native
    reset_policy: snapshot_then_seed
    reset_requirements:
      baseline_snapshot: clean-base
      requires_task_seed: false
    device_backend: adb_appium
    required_env: []
    supported_agent_ids: [dummy_text_agent]
matrix:
  expand: agent_x_benchmark
  seeds: [seed-0001]
runtime:
  batch_size: 1
  default_worker_mode: in_process
  observation_mode: text_only
  env_isolation: host
  max_steps: 10
  timeout_sec: 30
devices:
  device_mode: existing_device
  adb_serial: emulator-5554
  avd_name: Pixel_6_API_34
  emulator_profiles:
    - id: api34_base
      base_avd_name: Pixel_6_API_34
      platform: android
      api_level: 34
      system_image: android-34/google_apis/x86_64
      snapshot_name: clean-base
      screen_size: 1080x2400
      tags: [baseline]
  default_profile: api34_base
  control_backend: adb_appium
reset:
  name: snapshot_then_seed
  scope: trial
  baseline_snapshot: clean-base
  allow_benchmark_seed: true
  healthcheck_timeout_sec: 30
retries:
  max_trial_retries: 0
  max_step_retries: 0
  backoff_sec: 0
  retry_on: []
artifacts:
  level: light
  root_dir: runs/
  persist_step_artifacts: false
  persist_logs: true
  persist_prompt_payloads: false
monitoring:
  cli_live_panel: false
  web_viewer: false
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "existing-device.yml"
            config_path.write_text(config_yaml, encoding="utf-8")
            spec = load_project_spec(config_path)

        self.assertEqual(spec.devices.device_mode.value, "existing_device")
        self.assertEqual(spec.devices.adb_serials, ("emulator-5554",))
        self.assertEqual(spec.devices.avd_names, ("Pixel_6_API_34",))

    def test_env_placeholders_expand_inside_project_config(self) -> None:
        config_yaml = """
project:
  name: env-demo
  run_name: env-demo-run
models:
  - id: ${PHONE_AGENT_MODEL:-fallback-model}
    provider: openai_compatible
    api_style: openai_chat
    modalities: [text, image]
    supports_image_input: true
    supports_tool_calling: false
    supports_json_mode: false
agents:
  - id: dummy_vision_agent
    variant: default
    model_ref: ${PHONE_AGENT_MODEL:-fallback-model}
    integration_mode: wrap
    required_modalities: [text, image]
    supported_modalities: [text, image]
    supported_model_protocols: [openai_chat]
    supports_tool_calling: false
    supports_image_input: true
    supports_json_mode: false
    requires_tool_calling: false
    requires_json_mode: false
    required_env: []
    action_schema: dummy_vision_action_v1
    prompt_contract_version: dummy.v1
benchmarks:
  - id: dummy_benchmark
    integration_mode: wrap
    task_source:
      kind: inline
      selector: default
    metric_schema:
      primary: task_success
      native: [task_success]
    scorer_ref: dummy.native
    reset_policy: snapshot_then_seed
    reset_requirements:
      baseline_snapshot: clean-base
      requires_task_seed: false
    device_backend: adb_appium
    required_env: []
    supported_agent_ids: [dummy_vision_agent]
matrix:
  expand: agent_x_benchmark
  seeds: [seed-0001]
runtime:
  batch_size: 1
  default_worker_mode: in_process
  observation_mode: image_text
  env_isolation: host
  max_steps: 3
  timeout_sec: 30
devices:
  emulator_profiles:
    - id: api34_base
      base_avd_name: Pixel_6_API_34
      platform: android
      api_level: 34
      system_image: android-34/google_apis/x86_64
      snapshot_name: clean-base
      screen_size: 1080x2400
      tags: [baseline]
  default_profile: api34_base
  control_backend: adb_appium
reset:
  name: snapshot_then_seed
  scope: trial
  baseline_snapshot: clean-base
  allow_benchmark_seed: true
  healthcheck_timeout_sec: 30
retries:
  max_trial_retries: 0
  max_step_retries: 0
  backoff_sec: 0
  retry_on: []
artifacts:
  level: light
  root_dir: runs/
  persist_step_artifacts: false
  persist_logs: true
  persist_prompt_payloads: false
monitoring:
  cli_live_panel: false
  web_viewer: false
"""
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            os.environ,
            {"PHONE_AGENT_MODEL": "Qwen/Qwen3-VL-235B-A22B-Instruct"},
            clear=False,
        ):
            config_path = Path(temp_dir) / "env-placeholder.yml"
            config_path.write_text(config_yaml, encoding="utf-8")
            spec = load_project_spec(config_path)

        self.assertEqual(spec.models[0].model_id, "Qwen/Qwen3-VL-235B-A22B-Instruct")
        self.assertEqual(spec.agents[0].model_ref, "Qwen/Qwen3-VL-235B-A22B-Instruct")

    def test_autoglm_mobilesafetybench_run_config_loads(self) -> None:
        spec = load_project_spec(ROOT / "configs" / "runs" / "autoglm_mobilesafetybench.yml")

        self.assertEqual(spec.project.name, "open-autoglm-mobilesafetybench")
        self.assertEqual(spec.models[0].provider, "openai_compatible")
        self.assertEqual(spec.agents[0].agent_id, "open_autoglm")
        self.assertEqual(spec.agents[0].integration_mode.value, "hybrid")
        self.assertEqual(spec.agents[0].supported_backends, ("adb_appium", "adb", "hdc", "ios_wda"))
        self.assertEqual(spec.benchmarks[0].benchmark_id, "mobilesafetybench")
        self.assertEqual(spec.benchmarks[0].supported_agent_ids, ("open_autoglm",))

    def test_mobile_agent_e_run_config_core_fields_load(self) -> None:
        spec = load_project_spec(ROOT / "configs" / "runs" / "mobile_agent_e_mobilesafetybench.yml")

        self.assertEqual(spec.project.name, "mobile-agent-e-mobilesafetybench")
        self.assertEqual(spec.models[0].provider, "openai_compatible")
        self.assertEqual(spec.agents[0].agent_id, "mobile_agent_e")
        self.assertEqual(spec.agents[0].integration_mode.value, "wrap")
        self.assertEqual(spec.agents[0].supported_backends, ("adb_appium", "adb"))
        self.assertEqual(spec.benchmarks[0].benchmark_id, "mobilesafetybench")
        self.assertEqual(spec.benchmarks[0].supported_agent_ids, ("mobile_agent_e",))

    def test_androidworld_benchmark_config_loads(self) -> None:
        spec = load_project_spec(ROOT / "configs" / "runs" / "androidworld_benchmark.yml")

        self.assertEqual(spec.project.name, "androidworld-benchmark")
        self.assertEqual(spec.agents[0].agent_id, "dummy_text_agent")
        self.assertEqual(spec.agents[0].supported_backends, ("adb",))
        self.assertEqual(spec.agents[0].supported_benchmarks, ("androidworld",))
        self.assertEqual(spec.benchmarks[0].benchmark_id, "androidworld")
        self.assertEqual(spec.benchmarks[0].device_backend, "adb")
        self.assertEqual(spec.benchmarks[0].reset_policy, "benchmark_native_reset")
        self.assertEqual(spec.benchmarks[0].options["suite_family"], "android")
        self.assertEqual(spec.benchmarks[0].options["tasks"], ["SimpleSmsSend"])
        self.assertEqual(spec.benchmarks[0].options["n_task_combinations"], 1)

    def test_androidworld_runtime_recipe_exposes_ports_and_launch_hints(self) -> None:
        spec = load_project_spec(ROOT / "configs" / "runs" / "androidworld_benchmark.yml")
        recipe = spec.build_runtime_recipe(spec.agents[0], spec.benchmarks[0])

        self.assertEqual(recipe.control_backend, "adb")
        self.assertEqual(recipe.ports["console_port"], 5554)
        self.assertEqual(recipe.ports["grpc_port"], 8554)
        self.assertEqual(
            recipe.launch_hints["benchmark_task_source_path"],
            "references/benchmarks/android_world",
        )
        self.assertEqual(recipe.launch_hints["worker_env_name"], "androidworld")
        self.assertEqual(
            recipe.launch_hints["requirements_file"],
            "references/benchmarks/android_world/requirements.txt",
        )
        benchmark_options = json.loads(recipe.launch_hints["benchmark_options_json"])
        self.assertEqual(benchmark_options["suite_family"], "android")
        self.assertEqual(benchmark_options["tasks"], ["SimpleSmsSend"])

    def test_open_autoglm_androidworld_run_config_loads(self) -> None:
        spec = load_project_spec(ROOT / "configs" / "runs" / "autoglm_androidworld.yml")

        self.assertEqual(spec.project.run_name, "open_autoglm__androidworld")
        self.assertEqual(spec.devices.device_mode.value, "existing_device")
        self.assertEqual(spec.devices.control_backend, "adb")
        self.assertEqual(spec.runtime.batch_size, 1)
        self.assertEqual(spec.runtime.max_steps, 30)
        self.assertEqual(spec.runtime.timeout_sec, 3600)
        self.assertEqual(spec.retries.max_trial_retries, 1)
        self.assertEqual(spec.agents[0].agent_id, "open_autoglm")
        self.assertEqual(spec.agents[0].supported_benchmarks, ("androidworld", "mobilesafetybench"))
        self.assertEqual(spec.benchmarks[0].benchmark_id, "androidworld")
        self.assertEqual(spec.benchmarks[0].supported_agent_ids, ("open_autoglm",))
        self.assertEqual(spec.benchmarks[0].options["suite_family"], "android_world")
        self.assertEqual(spec.benchmarks[0].options["tasks"], "")
        self.assertEqual(len(spec.pair_runtime_recipes), 1)
        self.assertEqual(spec.pair_runtime_recipes[0].bridge_id, "open_autoglm__androidworld")
        recipe = spec.build_runtime_recipe(spec.agents[0], spec.benchmarks[0])
        self.assertEqual(recipe.bridge_id, "open_autoglm__androidworld")
        self.assertEqual(recipe.control_backend, "adb")
        self.assertEqual(recipe.ports["console_port"], 5554)
        self.assertEqual(recipe.ports["grpc_port"], 8554)

    def test_mobile_agent_e_run_config_loads(self) -> None:
        spec = load_project_spec(
            ROOT / "configs" / "runs" / "mobile_agent_e_mobilesafetybench.yml"
        )

        self.assertEqual(spec.project.run_name, "mobile_agent_e__mobilesafetybench")
        self.assertEqual(spec.devices.device_mode.value, "existing_device")
        self.assertEqual(spec.runtime.batch_size, 1)
        self.assertEqual(spec.runtime.max_steps, 20)
        self.assertEqual(spec.runtime.timeout_sec, 2400)
        self.assertEqual(spec.retries.max_trial_retries, 1)
        self.assertEqual(spec.agents[0].agent_id, "mobile_agent_e")
        self.assertEqual(spec.agents[0].supported_benchmarks, ("mobilesafetybench",))
        self.assertEqual(spec.benchmarks[0].supported_agent_ids, ("mobile_agent_e",))
        self.assertEqual(spec.benchmarks[0].task_source.selector, "all")
        self.assertEqual(len(spec.pair_runtime_recipes), 1)
        self.assertEqual(spec.pair_runtime_recipes[0].bridge_id, "mobile_agent_e__mobilesafetybench")
        self.assertEqual(
            spec.pair_runtime_recipes[0].recipe_id,
            "mobile_agent_e_mobilesafetybench_existing_device",
        )

    def test_mobile_agent_e_run_config_supports_smoke_overrides(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SNOWL_TASK_SELECTOR": "task_category=text_message_sending,task_id=low_risk_001,limit=1",
            },
            clear=False,
        ):
            spec = load_project_spec(
                ROOT / "configs" / "runs" / "mobile_agent_e_mobilesafetybench.yml"
            )

        self.assertEqual(spec.benchmarks[0].task_source.selector, "task_category=text_message_sending,task_id=low_risk_001,limit=1")
        self.assertEqual(spec.runtime.max_steps, 20)
        self.assertEqual(spec.runtime.timeout_sec, 2400)
        self.assertEqual(spec.retries.max_trial_retries, 1)

    def test_mobile_agent_e_androidworld_run_config_loads(self) -> None:
        spec = load_project_spec(
            ROOT / "configs" / "runs" / "mobile_agent_e_androidworld.yml"
        )

        self.assertEqual(spec.project.run_name, "mobile_agent_e__androidworld")
        self.assertEqual(spec.devices.device_mode.value, "existing_device")
        self.assertEqual(spec.runtime.batch_size, 1)
        self.assertEqual(spec.runtime.max_steps, 20)
        self.assertEqual(spec.runtime.timeout_sec, 3600)
        self.assertEqual(spec.retries.max_trial_retries, 1)
        self.assertEqual(spec.benchmarks[0].options["suite_family"], "android_world")
        self.assertEqual(spec.benchmarks[0].options["tasks"], "")
        recipe = spec.build_runtime_recipe(spec.agents[0], spec.benchmarks[0])
        self.assertEqual(recipe.bridge_id, "mobile_agent_e__androidworld")
        self.assertEqual(recipe.launch_hints["run_scope"], "full_suite")
        self.assertEqual(recipe.launch_hints["resume_strategy"], "reuse_output_dir")

    def test_mobile_agent_e_androidworld_run_config_supports_smoke_overrides(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SNOWL_ANDROIDWORLD_SUITE_FAMILY": "android",
                "SNOWL_ANDROIDWORLD_TASKS": "SimpleSmsSend",
            },
            clear=False,
        ):
            spec = load_project_spec(
                ROOT / "configs" / "runs" / "mobile_agent_e_androidworld.yml"
            )

        self.assertEqual(spec.project.run_name, "mobile_agent_e__androidworld")
        self.assertEqual(spec.devices.control_backend, "adb")
        self.assertEqual(spec.runtime.max_steps, 20)
        self.assertEqual(spec.runtime.timeout_sec, 3600)
        self.assertEqual(spec.retries.max_trial_retries, 1)
        self.assertEqual(spec.benchmarks[0].options["suite_family"], "android")
        self.assertEqual(spec.benchmarks[0].options["tasks"], "SimpleSmsSend")
        recipe = spec.build_runtime_recipe(spec.agents[0], spec.benchmarks[0])
        self.assertEqual(recipe.bridge_id, "mobile_agent_e__androidworld")
        self.assertEqual(recipe.launch_hints["run_scope"], "full_suite")
    def test_mobile_agent_v3_5_run_config_loads(self) -> None:
        spec = load_project_spec(
            ROOT / "configs" / "runs" / "mobile_agent_v3_5_mobilesafetybench.yml"
        )

        self.assertEqual(spec.project.run_name, "mobile_agent_v3_5__mobilesafetybench")
        self.assertEqual(spec.devices.device_mode.value, "existing_device")
        self.assertEqual(spec.runtime.batch_size, 1)
        self.assertEqual(spec.runtime.max_steps, 20)
        self.assertEqual(spec.runtime.timeout_sec, 2400)
        self.assertEqual(spec.retries.max_trial_retries, 1)
        self.assertEqual(spec.agents[0].agent_id, "mobile_agent_v3_5")
        self.assertEqual(spec.benchmarks[0].supported_agent_ids, ("mobile_agent_v3_5",))
        self.assertEqual(spec.benchmarks[0].task_source.selector, "all")
        self.assertEqual(len(spec.pair_runtime_recipes), 1)
        self.assertEqual(
            spec.pair_runtime_recipes[0].bridge_id,
            "mobile_agent_v3_5__mobilesafetybench",
        )
        self.assertEqual(
            spec.pair_runtime_recipes[0].recipe_id,
            "mobile_agent_v3_5_mobilesafetybench_existing_device",
        )

    def test_mobile_agent_v3_5_run_config_supports_smoke_overrides(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SNOWL_TASK_SELECTOR": "task_category=text_message_forwarding,task_id=low_risk_001,limit=1",
            },
            clear=False,
        ):
            spec = load_project_spec(
                ROOT / "configs" / "runs" / "mobile_agent_v3_5_mobilesafetybench.yml"
            )

        self.assertEqual(
            spec.benchmarks[0].task_source.selector,
            "task_category=text_message_forwarding,task_id=low_risk_001,limit=1",
        )
        self.assertEqual(spec.runtime.max_steps, 20)
        self.assertEqual(spec.runtime.timeout_sec, 2400)
        self.assertEqual(spec.retries.max_trial_retries, 1)

    def test_mobile_agent_v3_5_androidworld_run_config_loads(self) -> None:
        spec = load_project_spec(
            ROOT / "configs" / "runs" / "mobile_agent_v3_5_androidworld.yml"
        )

        self.assertEqual(spec.project.run_name, "mobile_agent_v3_5__androidworld")
        self.assertEqual(spec.devices.device_mode.value, "existing_device")
        self.assertEqual(spec.runtime.batch_size, 1)
        self.assertEqual(spec.runtime.max_steps, 20)
        self.assertEqual(spec.runtime.timeout_sec, 3600)
        self.assertEqual(spec.retries.max_trial_retries, 1)
        self.assertEqual(spec.benchmarks[0].options["suite_family"], "android_world")
        self.assertEqual(spec.benchmarks[0].options["tasks"], "")
        recipe = spec.build_runtime_recipe(spec.agents[0], spec.benchmarks[0])
        self.assertEqual(recipe.bridge_id, "mobile_agent_v3_5__androidworld")
        self.assertEqual(recipe.launch_hints["run_scope"], "full_suite")
        self.assertEqual(recipe.launch_hints["resume_strategy"], "reuse_output_dir")

    def test_mobile_agent_v3_5_androidworld_run_config_supports_smoke_overrides(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SNOWL_ANDROIDWORLD_SUITE_FAMILY": "android",
                "SNOWL_ANDROIDWORLD_TASKS": "SimpleSmsSend",
            },
            clear=False,
        ):
            spec = load_project_spec(
                ROOT / "configs" / "runs" / "mobile_agent_v3_5_androidworld.yml"
            )

        self.assertEqual(spec.project.run_name, "mobile_agent_v3_5__androidworld")
        self.assertEqual(spec.devices.control_backend, "adb")
        self.assertEqual(spec.runtime.max_steps, 20)
        self.assertEqual(spec.runtime.timeout_sec, 3600)
        self.assertEqual(spec.retries.max_trial_retries, 1)
        self.assertEqual(spec.benchmarks[0].options["suite_family"], "android")
        self.assertEqual(spec.benchmarks[0].options["tasks"], "SimpleSmsSend")
        recipe = spec.build_runtime_recipe(spec.agents[0], spec.benchmarks[0])
        self.assertEqual(recipe.bridge_id, "mobile_agent_v3_5__androidworld")
        self.assertEqual(recipe.launch_hints["run_scope"], "full_suite")
