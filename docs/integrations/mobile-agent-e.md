# Mobile-Agent-E Integration

This document records the current wrap-first integration state for `Mobile-Agent-E`.

## Local repository path

- expected clone path: `references/agents/MobileAgent/Mobile-Agent-E/`
- optional override env: `MOBILE_AGENT_E_HOME`

## Upstream structure analysis

- observation modality:
  - `text + image`
  - screenshots are the primary observation source
  - OCR and icon grounding are assembled inside `inference_agent_E.py::Perceptor.get_perception_infos`
  - reflection also depends on before/after screenshots
- action output form:
  - JSON action objects such as `{"name":"Tap","arguments":{"x":100,"y":200}}`
  - parsed through `MobileAgentE/agents.py::Operator.parse_response` and `MobileAgentE/agents.py::extract_json_object`
  - shortcut actions such as `Tap_Type_and_Enter` are part of the upstream action surface
- model dependency:
  - reasoning uses `BACKBONE_TYPE + provider API key` and calls `MobileAgentE/api.py::inference_chat`
  - perception uses a second caption/perceptor path with `QWEN_API_KEY`
  - the upstream repo still hardcodes reasoning model names and base URLs in `inference_agent_E.py`
- device backend:
  - upstream-native backend is `adb`
  - direct actions are implemented in `MobileAgentE/controller.py`
  - special text input still assumes ADB keyboard style tooling on device

## Recommended integration mode

- current adapter phase: `wrap`
- likely future real benchmark phase: `hybrid` via a dedicated pair bridge

Reasoning:

- the repo is centered on `run.py` and `inference_agent_E.py`, which own the full perception, planning, reflection, and logging loop;
- some internal modules are reusable, but doing a deep native split now would be risky and unnecessary for a minimal platform integration;
- a wrap-first adapter keeps `AgentSpec`, compatibility, config mapping, and mock artifact capture under platform control without disturbing the existing real `Open-AutoGLM x MobileSafetyBench` path.

## What is implemented in this phase

- registered adapter id: `mobile_agent_e`
- capability declaration and repository contract
- backend-aware and vision-aware compatibility checks
- wrap-side env mapping declaration for:
  - `provider -> BACKBONE_TYPE`
  - `model_id -> MOBILE_AGENT_E_REASONING_MODEL`
  - `base_url -> MOBILE_AGENT_E_BASE_URL`
  - `api_key -> MOBILE_AGENT_E_API_KEY`
  - `caption api/model -> MOBILE_AGENT_E_CAPTION_API_KEY / MOBILE_AGENT_E_CAPTION_MODEL`
- fallback mapping for the first smoke run:
  - `PHONE_AGENT_BASE_URL -> MOBILE_AGENT_E_BASE_URL` when the override is empty
  - `PHONE_AGENT_API_KEY -> MOBILE_AGENT_E_API_KEY` when the override is empty
  - `PHONE_AGENT_MODEL -> MOBILE_AGENT_E_REASONING_MODEL` when the override is empty
- action normalization into platform `ActionRecord`
- mock wrapped run and raw artifact capture under `raw/mobile_agent_e/`
- real wrap-first subprocess runner that calls upstream `run_single_task()` without modifying the third-party repo
- platform-driven `run` integration through the standard orchestrator path
- MobileSafetyBench task context forwarding for `initial_device_status`, `evaluation`, and `action_space`, with benchmark-aware instruction composition on the wrapper side
- dedicated `mobile_agent_e__mobilesafetybench` pair bridge for MobileSafetyBench reset/seed/bootstrap and pair-level raw artifacts
- raw output capture for:
  - `raw/mobile_agent_e_mobilesafetybench/bridge_request.json`
  - `raw/mobile_agent_e_mobilesafetybench/environment_init.console.txt`
  - `raw/mobile_agent_e_mobilesafetybench/final_result.json`
  - `raw/mobile_agent_e_mobilesafetybench/steps/*.console.txt`
  - `raw/mobile_agent_e_mobilesafetybench/steps/*.model_response.{txt,json}`
  - `request.json`
  - `task_payload.json`
  - `benchmark_context.json`
  - `runner_request.json`
  - `runner_result.json`
  - `wrapped_result.json`
  - `steps/*.model_response.{txt,json}`
  - top-level `steps/*.jpg|xml` now prefer the post-action observation that follows each Mobile-Agent-E action, which is closer to the existing Open-AutoGLM pair artifact layout
- canonical checked-in run config: [configs/runs/mobile_agent_e_mobilesafetybench.yml](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/configs/runs/mobile_agent_e_mobilesafetybench.yml)
- canonical real run config: [mobile_agent_e_mobilesafetybench.yml](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/configs/runs/mobile_agent_e_mobilesafetybench.yml)

## Repository inspection commands

```bash
PYTHONPATH=src python3 -m snowl_mobile inspect-repo agent references/agents/MobileAgent/Mobile-Agent-E
PYTHONPATH=src python3 -m snowl_mobile registry list-agents --metadata
```

For the canonical full run, prefer:

- pass `--base-url`, `--api-key`, `--model-name`, and `--max-steps` directly on the `snowl-mobile run` command
- set `MOBILE_AGENT_E_HOME=<repo path>`
- rely on the platform's default lightweight perception, or set `MOBILE_AGENT_E_LIGHTWEIGHT_PERCEPTION=0` only if you intentionally want the full perception stack
- `MOBILE_AGENT_E_ADB_PATH=<full path to adb>` if the default `adb` command does not see your emulator

Only add `MOBILE_AGENT_E_BASE_URL`, `MOBILE_AGENT_E_API_KEY`, or `MOBILE_AGENT_E_REASONING_MODEL` if Mobile-Agent-E should use a different reasoning endpoint from Open-AutoGLM. The user-facing workflow should now be the single canonical full-run command below.

Canonical full-run command:

```bash
snowl-mobile run configs/runs/mobile_agent_e_mobilesafetybench.yml \
  --model-name <model-name> \
  --base-url <base-url> \
  --api-key '<api-key>' \
  --max-steps 20 \
  --batch-size 3 \
  --device-mode existing_device \
  --adb-serial emulator-5556 \
  --adb-serial emulator-5558 \
  --adb-serial emulator-5560 \
  --output-dir ./tmp/snowl-mobile-mobile-agent-e-mobilesafetybench
```

## Current limitations

- the real pair now uses a dedicated bridge for MobileSafetyBench reset/seed and final-state evaluation, but the agent execution itself still goes through a platform-side subprocess wrapper around upstream `run_single_task()`, and step-by-step evaluator progress is not yet synchronized with every Mobile-Agent-E action because the upstream runner owns its own ADB loop;
- `trial.log`, `steps/*.jpg|xml`, and `raw/mobile_agent_e_mobilesafetybench/steps/*.console.txt` now materialize incrementally as completed steps are observed in the upstream transcript, but they are still reconstructed from the wrapped subprocess output rather than emitted directly from `MobileSafetyEnv.step()`;
- the upstream repo still hardcodes several reasoning model names and base URLs, so the wrapper patches module globals at launch time;
- the normalized platform contract currently standardizes only `openai_chat` reasoning models even though the upstream repo also has provider-specific Gemini and Claude branches;
- the upstream dependency stack is heavier than the current platform default environment, and the upstream README still recommends Python 3.10, so a dedicated worker env remains the expected next step;
- the wrapper now forwards benchmark task context into the prompt and artifacts, but evaluator progress is still not updated step-by-step the way the Open-AutoGLM bridge path does it.
- full-task runs do land unified `summary.json`, per-trial `score.json`, `trajectory.json`, and `raw/mobile_agent_e/` artifacts under the platform run directory, but operational stability still depends on the host environment, adb/Appium health, and the model endpoint.
