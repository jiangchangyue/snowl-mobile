# Mobile-Agent-v3.5 Integration

Current status: `mobile_agent_v3_5` is registered as a real agent adapter, has a platform-owned subprocess wrapper, and now also has a dedicated `mobile_agent_v3_5__mobilesafetybench` pair bridge for MobileSafetyBench.

## Current shape

- upstream repo path: `references/agents/MobileAgent/Mobile-Agent-v3.5/`
- adapter id: `mobile_agent_v3_5`
- current integration mode: `wrap`
- pair bridge id: `mobile_agent_v3_5__mobilesafetybench`
- current upstream focus: `Mobile-Agent-v3.5/mobile_use/`
- minimal config: [configs/integrations/mobile_agent_v3_5/minimal.yml](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/configs/integrations/mobile_agent_v3_5/minimal.yml)
- full run config: [configs/runs/mobile_agent_v3_5_mobilesafetybench.yml](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/configs/runs/mobile_agent_v3_5_mobilesafetybench.yml)

## Why `mobile_use/`

- `mobile_use/` is the real Android device path that already uses ADB plus screenshot-driven prompting.
- It is much lighter than `android_world_v3.5/` and does not force AndroidWorld task/env semantics into the platform.
- The upstream model call contract is already OpenAI-compatible enough for the platform to map `base_url`, `api_key`, and `model` without changing core schemas.
- The platform wrapper can reuse upstream helpers while avoiding the upstream CLI's interactive `input()` branches and local output-directory deletion behavior.

## Runtime shape

- planner/orchestrator path: pair bridge for real/fake MobileSafetyBench runs
- benchmark bootstrap: `mobile_agent_v3_5__mobilesafetybench`
- runner entry: `snowl_mobile.adapters.agents.mobile_agent_v3_5_runner`
- upstream helpers reused inside the runner:
  - `mobile_use/utils.py::AdbTools`
  - `mobile_use/utils.py::build_messages`
  - `mobile_use/utils.py::GUIOwlWrapper.predict_mm`
  - `mobile_use/run_gui_owl_1_5_for_mobile.py::parse_action`
  - `mobile_use/run_gui_owl_1_5_for_mobile.py::rescale_coordinates`

The wrapper intentionally stays close to upstream agent behavior:

- the platform binds the already-running device and benchmark environment
- the runner executes Mobile-Agent-v3.5's parsed actions as-is, with only environment/execution translation that is required to make those actions runnable
- the platform does not rewrite Mobile-Agent-v3.5 decisions into benchmark-specific fallback actions

## Env mapping

Dedicated env vars take precedence:

- `MOBILE_AGENT_V3_5_HOME`
- `MOBILE_AGENT_V3_5_API_KEY`
- `MOBILE_AGENT_V3_5_BASE_URL`
- `MOBILE_AGENT_V3_5_MODEL`
- `MOBILE_AGENT_V3_5_ADB_PATH`

Optional app-resolver overrides:

- `MOBILE_AGENT_V3_5_APP_RESOLVER_API_KEY`
- `MOBILE_AGENT_V3_5_APP_RESOLVER_BASE_URL`
- `MOBILE_AGENT_V3_5_APP_RESOLVER_MODEL`

Fallbacks for the first smoke setup:

- `PHONE_AGENT_API_KEY`
- `PHONE_AGENT_BASE_URL`
- `PHONE_AGENT_MODEL`

## Validation commands

```bash
PYTHONPATH=src python3 -m snowl_mobile registry list-agents --metadata
PYTHONPATH=src python3 -m snowl_mobile validate-config configs/integrations/mobile_agent_v3_5/minimal.yml
PYTHONPATH=src python3 -m snowl_mobile plan configs/integrations/mobile_agent_v3_5/minimal.yml
PYTHONPATH=src python3 -m snowl_mobile dry-run configs/integrations/mobile_agent_v3_5/minimal.yml --output-dir /tmp/snowl-mobile-mobile-agent-v3-5
```

## Real smoke commands

```bash
export SNOWL_TASK_SELECTOR='task_category=text_message_sending,task_id=low_risk_001,limit=1'
PYTHONPATH=src python3 -m snowl_mobile validate-config configs/runs/mobile_agent_v3_5_mobilesafetybench.yml
PYTHONPATH=src python3 -m snowl_mobile plan configs/runs/mobile_agent_v3_5_mobilesafetybench.yml
PYTHONPATH=src python3 -m snowl_mobile run configs/runs/mobile_agent_v3_5_mobilesafetybench.yml --device-mode existing_device --adb-serial emulator-5554 --output-dir /tmp/snowl-mobile-mobile-agent-v3-5-smoke
PYTHONPATH=src python3 -m snowl_mobile summarize /tmp/snowl-mobile-mobile-agent-v3-5-smoke
unset SNOWL_TASK_SELECTOR
```

## Full-run commands

```bash
PYTHONPATH=src python3 -m snowl_mobile validate-config configs/runs/mobile_agent_v3_5_mobilesafetybench.yml
PYTHONPATH=src python3 -m snowl_mobile plan configs/runs/mobile_agent_v3_5_mobilesafetybench.yml
PYTHONPATH=src python3 -m snowl_mobile run configs/runs/mobile_agent_v3_5_mobilesafetybench.yml --device-mode existing_device --adb-serial emulator-5554 --output-dir /tmp/snowl-mobile-mobile-agent-v3-5-full
PYTHONPATH=src python3 -m snowl_mobile summarize /tmp/snowl-mobile-mobile-agent-v3-5-full
```

For a platform-only smoke path:

```bash
export SNOWL_TASK_SELECTOR='task_category=text_message_sending,task_id=low_risk_001,limit=1'
PYTHONPATH=src python3 -m snowl_mobile run configs/runs/mobile_agent_v3_5_mobilesafetybench.yml --device-mode fake --output-dir /tmp/snowl-mobile-mobile-agent-v3-5-fake
unset SNOWL_TASK_SELECTOR
```

## Artifacts

Look under:

- `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5_mobilesafetybench/bridge_request.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5_mobilesafetybench/environment_init.console.txt`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5_mobilesafetybench/bootstrap_observation.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5_mobilesafetybench/final_observation.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5_mobilesafetybench/final_result.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5/request.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5/task_payload.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5/benchmark_context.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5/runner_request.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5/runner_result.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5/wrapped_result.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5/steps/0001.model_response.txt`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5/steps/0001.model_response.json`
- `<run_dir>/trials/<trial_id>/trajectory.json`
- `<run_dir>/trials/<trial_id>/score.json`

## Current limits

- evaluator progress is still reconciled mainly at bootstrap/final-state boundaries because Mobile-Agent-v3.5 does not act through `MobileSafetyEnv.step()`
- benchmark-aware open-app aliasing is bridge-owned but intentionally minimal
- because the platform no longer rewrites upstream Mobile-Agent-v3.5 decisions, some task failures now surface more faithfully as raw agent behavior instead of wrapper-assisted completions
- no dedicated worker env yet
- the real path still depends on the host Python environment and on upstream `mobile_use` dependencies
- the canonical full config defaults to `all`, which is `250` tasks in the current MobileSafetyBench checkout
- start with a one-task `SNOWL_TASK_SELECTOR` override before the full-manifest default; if the smoke path is unstable, the full run will mostly amplify that instability
- keep `batch_size=1`, `artifact level = standard`, and `device_mode = existing_device` for now
