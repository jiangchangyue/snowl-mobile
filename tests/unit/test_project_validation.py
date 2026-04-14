from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from snowl_mobile.core.config_loader import load_project_spec
from snowl_mobile.core.errors import ConfigError


class ProjectValidationTestCase(unittest.TestCase):
    def test_invalid_agent_model_protocol_raises_friendly_error(self) -> None:
        invalid_yaml = """
project:
  name: invalid-demo
  run_name: invalid-run
models:
  - id: mock-model
    provider: openai
    api_style: incompatible_protocol
    modalities: [text]
    supports_image_input: false
    supports_tool_calling: false
    supports_json_mode: false
agents:
  - id: mock-agent
    model_ref: mock-model
    integration_mode: wrap
    required_modalities: [text]
    supported_modalities: [text]
    supported_model_protocols: [openai_chat]
    supports_tool_calling: false
    supports_image_input: false
    supports_json_mode: false
    required_env: []
    action_schema: demo
    prompt_contract_version: v1
benchmarks:
  - id: mock-benchmark
    integration_mode: wrap
    task_source:
      kind: inline
    metric_schema:
      primary: success
      native: [success]
    scorer_ref: mock.native
    reset_policy: baseline
    reset_requirements: {}
    device_backend: adb
    required_env: []
    supported_agent_ids: [mock-agent]
matrix:
  expand: agent_x_benchmark
  seeds: [seed-1]
runtime:
  batch_size: 1
  default_worker_mode: in_process
  observation_mode: text_only
  env_isolation: host
  max_steps: 5
  timeout_sec: 60
devices:
  emulator_profiles:
    - id: emulator-1
      base_avd_name: base
      platform: android
      api_level: 34
      system_image: image
      snapshot_name: clean
      screen_size: 1080x2400
      tags: [baseline]
  default_profile: emulator-1
  control_backend: adb
reset:
  name: baseline
  scope: trial
  baseline_snapshot: clean
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
            path = Path(temp_dir) / "invalid.yml"
            path.write_text(invalid_yaml, encoding="utf-8")
            with self.assertRaises(ConfigError) as context:
                load_project_spec(path)

        self.assertIn("agents[0]", str(context.exception))
        self.assertIn("supported_model_protocols", str(context.exception))

    def test_invalid_benchmark_reset_policy_is_rejected(self) -> None:
        invalid_yaml = """
project:
  name: invalid-demo
  run_name: invalid-run
models:
  - id: mock-model
    provider: openai
    api_style: openai_chat
    modalities: [text]
    supports_image_input: false
    supports_tool_calling: false
    supports_json_mode: false
agents:
  - id: mock-agent
    model_ref: mock-model
    integration_mode: wrap
    required_modalities: [text]
    supported_modalities: [text]
    supported_model_protocols: [openai_chat]
    supports_tool_calling: false
    supports_image_input: false
    supports_json_mode: false
    required_env: []
    action_schema: demo
    prompt_contract_version: v1
benchmarks:
  - id: mock-benchmark
    integration_mode: wrap
    task_source:
      kind: inline
    metric_schema:
      primary: success
      native: [success]
    scorer_ref: mock.native
    reset_policy: wrong-policy
    reset_requirements: {}
    device_backend: adb
    required_env: []
    supported_agent_ids: [mock-agent]
matrix:
  expand: agent_x_benchmark
  seeds: [seed-1]
runtime:
  batch_size: 1
  default_worker_mode: in_process
  observation_mode: text_only
  env_isolation: host
  max_steps: 5
  timeout_sec: 60
devices:
  emulator_profiles:
    - id: emulator-1
      base_avd_name: base
      platform: android
      api_level: 34
      system_image: image
      snapshot_name: clean
      screen_size: 1080x2400
      tags: [baseline]
  default_profile: emulator-1
  control_backend: adb
reset:
  name: baseline
  scope: trial
  baseline_snapshot: clean
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
            path = Path(temp_dir) / "invalid.yml"
            path.write_text(invalid_yaml, encoding="utf-8")
            with self.assertRaises(ConfigError) as context:
                load_project_spec(path)

        self.assertIn("benchmarks[0].reset_policy", str(context.exception))
