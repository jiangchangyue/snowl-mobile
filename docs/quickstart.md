# Quickstart

This quickstart is for a new user who wants the shortest path to the first real run.

## 1. Install the platform

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
```

## 2. Clone the required third-party repos

```bash
git clone <Open-AutoGLM-url> references/agents/Open-AutoGLM
git clone <MobileSafetyBench-url> references/benchmarks/mobilesafetybench
```

## 3. Install upstream requirements into the same environment

```bash
python -m pip install -r references/agents/Open-AutoGLM/requirements.txt
python -m pip install -r references/benchmarks/mobilesafetybench/requirements.txt
python -m pip install -r references/agents/MobileAgent/Mobile-Agent-E/requirements.txt
python -m pip install openai pillow numpy
```

## 4. Prepare runtime inputs

The CLI no longer auto-loads `.env` or `.env.local`.

The platform auto-detects repo locations under `references/` and will reuse `appium` from `PATH` when available. For most first runs, you only need to provide model endpoint settings yourself, either through shell exports or directly on the command line.

## 5. Start an Android emulator manually

The current first real run path uses `existing_device`, so the platform expects an already running emulator.

Check:

```bash
adb devices
```

## 6. Verify discovery

```bash
snowl-mobile registry list-agents
snowl-mobile registry list-benchmarks
snowl-mobile devices list --config configs/runs/autoglm_mobilesafetybench.yml --device-mode existing_device
snowl-mobile devices health-check --config configs/runs/autoglm_mobilesafetybench.yml --device-mode existing_device
```

## 7. Run the first real pair

```bash
snowl-mobile validate-config configs/runs/autoglm_mobilesafetybench.yml
snowl-mobile plan configs/runs/autoglm_mobilesafetybench.yml
snowl-mobile run configs/runs/autoglm_mobilesafetybench.yml \
  --model-name Qwen2.5-VL-72B-Instruct \
  --base-url https://your-openai-compatible-endpoint/v1 \
  --api-key <your-api-key> \
  --max-steps 20 \
  --device-mode existing_device \
  --adb-serial emulator-5554 \
  --output-dir /tmp/snowl-mobile-real-pair
snowl-mobile summarize /tmp/snowl-mobile-real-pair
```

`--output-dir` is the run directory itself. Reusing the same path resumes the run automatically, reuses completed/skipped trials, and reruns failed or partial ones.

This checked-in config now defaults to all MobileSafetyBench tasks. For a small smoke run, set:

```bash
export SNOWL_TASK_SELECTOR='task_category=text_message_sending,task_id=high_risk_001,limit=1'
```

You can also edit `benchmarks[*].task_source.selector` directly. `limit=-1` means no limit.

Each selected task becomes a separate trial, and the platform applies the configured reset flow again before the next trial.

To keep two existing emulators busy in parallel and automatically refill whichever one finishes first:

```bash
snowl-mobile run configs/runs/autoglm_mobilesafetybench.yml \
  --model-name Qwen2.5-VL-72B-Instruct \
  --base-url https://your-openai-compatible-endpoint/v1 \
  --api-key <your-api-key> \
  --max-steps 20 \
  --batch-size 2 \
  --device-mode existing_device \
  --adb-serial emulator-5556 \
  --adb-serial emulator-5560 \
  --output-dir /tmp/snowl-mobile-autoglm-mobilesafetybench-batch2
```

`batch_size` now controls true platform scheduling for `run`: the orchestrator starts one task per available emulator up to the batch size limit, and when one emulator goes idle the next queued task is leased onto it immediately.

## 8. Inspect artifacts

Look under:

- `/tmp/snowl-mobile-real-pair/run.log`
- `run.log` now shows the dynamic process: reset, bridge execution, per-step progress, and final score export
- `/tmp/snowl-mobile-real-pair/summary.json`
- `/tmp/snowl-mobile-real-pair/trials/<trial_id>/score.json`
- `score.json` is the platform-facing MobileSafetyBench evaluation output for that task
- `/tmp/snowl-mobile-real-pair/trials/<trial_id>/trajectory.json`
- `trajectory.json` is a concise user-facing trace: task instruction, Thought, Action, Action Input, summarized observation, and screenshot/XML paths
- `/tmp/snowl-mobile-real-pair/trials/<trial_id>/raw/open_autoglm_mobilesafetybench/steps/0001.model_response.txt`
- `/tmp/snowl-mobile-real-pair/trials/<trial_id>/raw/open_autoglm_mobilesafetybench/steps/0001.model_response.json`
- `/tmp/snowl-mobile-real-pair/trials/<trial_id>/steps/0001.png`
- `/tmp/snowl-mobile-real-pair/trials/<trial_id>/steps/0001.xml`

## 8b. Optional: validate AndroidWorld on the benchmark side first

AndroidWorld is now integrated as a benchmark-side path before the first agent bridge lands.

Recommended order:

1. Create a dedicated AndroidWorld Python environment and point `ANDROID_WORLD_PYTHON` at it.
2. Start the emulator from the command line with gRPC enabled.
3. Run `benchmark-setup` once on the target emulator.
4. Run `benchmark-run` to validate task bootstrap, observation capture, and native scoring.

Example emulator launch:

```bash
emulator -avd AndroidWorldAvd -no-snapshot -grpc 8554
```

Example commands:

```bash
snowl-mobile validate-config configs/runs/androidworld_benchmark.yml
snowl-mobile plan configs/runs/androidworld_benchmark.yml
snowl-mobile benchmark-setup configs/runs/androidworld_benchmark.yml --device-mode existing_device --adb-serial emulator-5554 --output-dir /tmp/snowl-mobile-androidworld-setup
snowl-mobile benchmark-run configs/runs/androidworld_benchmark.yml --device-mode existing_device --adb-serial emulator-5554 --output-dir /tmp/snowl-mobile-androidworld-benchmark
```

Look under:

- `/tmp/snowl-mobile-androidworld-setup/trials/<trial_id>/raw/androidworld/setup.request.json`
- `/tmp/snowl-mobile-androidworld-setup/trials/<trial_id>/raw/androidworld/setup.result.json`
- `/tmp/snowl-mobile-androidworld-benchmark/trials/<trial_id>/raw/androidworld/probe.request.json`
- `/tmp/snowl-mobile-androidworld-benchmark/trials/<trial_id>/raw/androidworld/probe.result.json`
- `/tmp/snowl-mobile-androidworld-benchmark/trials/<trial_id>/raw/androidworld/ui_tree.json`
- `/tmp/snowl-mobile-androidworld-benchmark/trials/<trial_id>/score.json`

`benchmark-run` does not execute an external agent yet, so `task_success` can remain `0` even when the benchmark-side bootstrap succeeded.

## 8c. Optional: run the first Open-AutoGLM x AndroidWorld real pair

This is now the canonical AndroidWorld real-pair path for Open-AutoGLM. Keep the first run tiny by overriding the suite/task selection.

Recommended order:

1. Point `ANDROID_WORLD_PYTHON` at a Python environment that has both AndroidWorld and Open-AutoGLM requirements installed.
2. Launch the emulator from the command line with gRPC enabled.
3. Run `benchmark-setup` once on a fresh emulator.
4. Validate the real-pair config in smoke mode.
5. Expand the smoke plan.
6. Run the pair and override `--batch-size` at the CLI when you want multiple emulators kept busy.
7. Summarize the run directory.

```bash
emulator -avd AndroidWorldAvd -no-snapshot -grpc 8554
adb devices

SNOWL_ANDROIDWORLD_SUITE_FAMILY=android \
SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend \
snowl-mobile validate-config configs/runs/autoglm_androidworld.yml
SNOWL_ANDROIDWORLD_SUITE_FAMILY=android \
SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend \
snowl-mobile plan configs/runs/autoglm_androidworld.yml
snowl-mobile benchmark-setup configs/runs/androidworld_benchmark.yml --device-mode existing_device --adb-serial emulator-5554 --output-dir /tmp/snowl-mobile-androidworld-setup
SNOWL_ANDROIDWORLD_SUITE_FAMILY=android \
SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend \
snowl-mobile run configs/runs/autoglm_androidworld.yml --device-mode existing_device --adb-serial emulator-5554 --output-dir /tmp/snowl-mobile-open-autoglm-androidworld
snowl-mobile summarize /tmp/snowl-mobile-open-autoglm-androidworld
```

Look under:

- `/tmp/snowl-mobile-open-autoglm-androidworld/summary.json`
- `/tmp/snowl-mobile-open-autoglm-androidworld/trials/<trial_id>/score.json`
- `/tmp/snowl-mobile-open-autoglm-androidworld/trials/<trial_id>/trajectory.json`
- `/tmp/snowl-mobile-open-autoglm-androidworld/trials/<trial_id>/raw/open_autoglm_androidworld/bridge_request.json`
- `/tmp/snowl-mobile-open-autoglm-androidworld/trials/<trial_id>/raw/open_autoglm_androidworld/final_result.json`
- `/tmp/snowl-mobile-open-autoglm-androidworld/trials/<trial_id>/raw/open_autoglm_androidworld/steps/0001.model_response.json`

Current limitation:

- the first bridge keeps Open-AutoGLM's action execution on ADB while AndroidWorld owns bootstrap and scoring, so this is a minimal closure rather than a full AndroidWorld-native action loop.

## 8d. Optional: expand Open-AutoGLM x AndroidWorld to the full suite

Only do this after the smoke path is stable on the same emulator and model endpoint.

Use the same checked-in config:

- `configs/runs/autoglm_androidworld.yml` for both smoke and full-suite runs

Current checkout behavior:

- default full-suite: `suite_family=android_world`, `tasks=[]`, `max_steps=30`, `timeout_sec=3600`, `max_trial_retries=1`
- smoke overrides: `SNOWL_ANDROIDWORLD_SUITE_FAMILY=android` and `SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend`
- the config keeps `artifact level = standard` and `existing_device`; use `--batch-size N` plus repeated `--adb-serial` flags for multi-emulator runs

Recommended order:

1. Keep the same dedicated `ANDROID_WORLD_PYTHON`.
2. Use a fresh `--output-dir` for the full run.
3. Watch `run.log` while the run is active.
4. Re-run `summarize` to inspect aggregate progress.

```bash
snowl-mobile validate-config configs/runs/autoglm_androidworld.yml
snowl-mobile plan configs/runs/autoglm_androidworld.yml
snowl-mobile run configs/runs/autoglm_androidworld.yml --device-mode existing_device --adb-serial emulator-5554 --output-dir /tmp/snowl-mobile-open-autoglm-androidworld-full
snowl-mobile summarize /tmp/snowl-mobile-open-autoglm-androidworld-full
```

Look under:

- `/tmp/snowl-mobile-open-autoglm-androidworld-full/run.log`
- `/tmp/snowl-mobile-open-autoglm-androidworld-full/summary.json`
- `/tmp/snowl-mobile-open-autoglm-androidworld-full/events.jsonl`
- `/tmp/snowl-mobile-open-autoglm-androidworld-full/trials/<trial_id>/trial.log`
- `/tmp/snowl-mobile-open-autoglm-androidworld-full/trials/<trial_id>/score.json`
- `/tmp/snowl-mobile-open-autoglm-androidworld-full/trials/<trial_id>/trajectory.json`
- `/tmp/snowl-mobile-open-autoglm-androidworld-full/trials/<trial_id>/raw/open_autoglm_androidworld/`

Keep `SNOWL_ANDROIDWORLD_CHECKPOINT_DIR` and `SNOWL_ANDROIDWORLD_OUTPUT_PATH` blank unless you explicitly want the upstream AndroidWorld outputs copied into each trial's raw artifact directory.

## 9. Optional: run Mobile-Agent-E through the same platform flow

This path is platform-driven and now uses the dedicated `mobile_agent_e__mobilesafetybench` pair bridge for MobileSafetyBench reset/seed and pair-level artifact capture.

Recommended order for the first real smoke run:

1. Start an Android emulator manually.
2. Run `adb devices` and confirm the target serial appears as `device`.
3. Make sure `MOBILE_AGENT_E_HOME` is resolvable and set `MOBILE_AGENT_E_LIGHTWEIGHT_PERCEPTION=1` for the first smoke run if needed.
4. Pass `--model-name`, `--base-url`, and `--api-key` on the CLI if you want to override the checked-in defaults without using shell environment variables.
5. If your shell can see the emulator but the CLI cannot, set `MOBILE_AGENT_E_ADB_PATH` to the exact SDK `adb` binary.
6. Run `validate-config`, then `plan`, then `run`, then `summarize`.

```bash
export SNOWL_TASK_SELECTOR='task_category=text_message_sending,task_id=low_risk_001,limit=1'
snowl-mobile validate-config configs/runs/mobile_agent_e_mobilesafetybench.yml
snowl-mobile plan configs/runs/mobile_agent_e_mobilesafetybench.yml
snowl-mobile run configs/runs/mobile_agent_e_mobilesafetybench.yml --device-mode existing_device --adb-serial emulator-5554 --output-dir /tmp/snowl-mobile-mobile-agent-e
snowl-mobile summarize /tmp/snowl-mobile-mobile-agent-e
```

The checked-in Mobile-Agent-E run config now defaults to the full manifest, and the one-task smoke run is selected through `SNOWL_TASK_SELECTOR`.

After the one-task smoke run is stable, switch back to the full-manifest default:

```bash
unset SNOWL_TASK_SELECTOR
snowl-mobile validate-config configs/runs/mobile_agent_e_mobilesafetybench.yml
snowl-mobile plan configs/runs/mobile_agent_e_mobilesafetybench.yml
snowl-mobile run configs/runs/mobile_agent_e_mobilesafetybench.yml --device-mode existing_device --adb-serial emulator-5554 --output-dir /tmp/snowl-mobile-mobile-agent-e-full
snowl-mobile summarize /tmp/snowl-mobile-mobile-agent-e-full
```

The unified config defaults to all 250 MobileSafetyBench tasks in this checkout. If you need to sample while keeping the same config shape, override:

```bash
export SNOWL_TASK_SELECTOR='task_category=text_message_sending,task_id=low_risk_001,limit=1'
```

Look under:

- `/tmp/snowl-mobile-mobile-agent-e/trials/<trial_id>/raw/mobile_agent_e_mobilesafetybench/bridge_request.json`
- `/tmp/snowl-mobile-mobile-agent-e/trials/<trial_id>/raw/mobile_agent_e_mobilesafetybench/environment_init.console.txt`
- `/tmp/snowl-mobile-mobile-agent-e/trials/<trial_id>/raw/mobile_agent_e_mobilesafetybench/final_result.json`
- `/tmp/snowl-mobile-mobile-agent-e/trials/<trial_id>/raw/mobile_agent_e/request.json`
- `/tmp/snowl-mobile-mobile-agent-e/trials/<trial_id>/raw/mobile_agent_e/task_payload.json`
- `/tmp/snowl-mobile-mobile-agent-e/trials/<trial_id>/raw/mobile_agent_e/benchmark_context.json`
- `/tmp/snowl-mobile-mobile-agent-e/trials/<trial_id>/raw/mobile_agent_e/runner_result.json`
- `/tmp/snowl-mobile-mobile-agent-e/trials/<trial_id>/trajectory.json`
- `/tmp/snowl-mobile-mobile-agent-e/trials/<trial_id>/score.json`

For full runs, use:

- `/tmp/snowl-mobile-mobile-agent-e-full/run.log` for live progress
- `/tmp/snowl-mobile-mobile-agent-e-full/summary.json` for current aggregate status
- `/tmp/snowl-mobile-mobile-agent-e-full/trials/<trial_id>/raw/mobile_agent_e/` for raw wrapped-agent outputs

## 9b. Optional: run Mobile-Agent-E on AndroidWorld through the same platform flow

This path now uses the dedicated `mobile_agent_e__androidworld` pair bridge and reuses the AndroidWorld benchmark adapter, bootstrap, scoring, and artifact layout.

Recommended order for the first real smoke run:

1. Launch the AndroidWorld emulator from the command line with `-grpc 8554`.
2. Run `adb devices` and confirm the target serial appears as `device`.
3. Keep `MOBILE_AGENT_E_HOME`, `ANDROID_WORLD_HOME`, and `ANDROID_WORLD_PYTHON` set.
4. Reuse `PHONE_AGENT_*` or provide `MOBILE_AGENT_E_API_KEY` and `MOBILE_AGENT_E_BASE_URL` if you want a different endpoint.
5. Start with the same config in smoke mode before using its default full-suite mode.

```bash
emulator -avd AndroidWorldAvd -no-snapshot -grpc 8554
adb devices

SNOWL_ANDROIDWORLD_SUITE_FAMILY=android SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend snowl-mobile validate-config configs/runs/mobile_agent_e_androidworld.yml
SNOWL_ANDROIDWORLD_SUITE_FAMILY=android SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend snowl-mobile plan configs/runs/mobile_agent_e_androidworld.yml
SNOWL_ANDROIDWORLD_SUITE_FAMILY=android SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend snowl-mobile run configs/runs/mobile_agent_e_androidworld.yml --device-mode existing_device --adb-serial emulator-5554 --output-dir /tmp/snowl-mobile-mobile-agent-e-androidworld
snowl-mobile summarize /tmp/snowl-mobile-mobile-agent-e-androidworld
```

After the smoke path is stable, switch to the same config without overrides:

```bash
snowl-mobile validate-config configs/runs/mobile_agent_e_androidworld.yml
snowl-mobile plan configs/runs/mobile_agent_e_androidworld.yml
snowl-mobile run configs/runs/mobile_agent_e_androidworld.yml --device-mode existing_device --adb-serial emulator-5554 --output-dir /tmp/snowl-mobile-mobile-agent-e-androidworld-full
snowl-mobile summarize /tmp/snowl-mobile-mobile-agent-e-androidworld-full
```

Look under:

- `/tmp/snowl-mobile-mobile-agent-e-androidworld-full/run.log`
- `/tmp/snowl-mobile-mobile-agent-e-androidworld-full/summary.json`
- `/tmp/snowl-mobile-mobile-agent-e-androidworld-full/trials/<trial_id>/score.json`
- `/tmp/snowl-mobile-mobile-agent-e-androidworld-full/trials/<trial_id>/trajectory.json`
- `/tmp/snowl-mobile-mobile-agent-e-androidworld-full/trials/<trial_id>/raw/mobile_agent_e_androidworld/bridge_request.json`
- `/tmp/snowl-mobile-mobile-agent-e-androidworld-full/trials/<trial_id>/raw/mobile_agent_e_androidworld/final_result.json`
- `/tmp/snowl-mobile-mobile-agent-e-androidworld-full/trials/<trial_id>/raw/mobile_agent_e/runner_result.json`

## 9c. Optional: run Mobile-Agent-v3.5 on AndroidWorld through the same platform flow

This path now uses the dedicated `mobile_agent_v3_5__androidworld` pair bridge and reuses the AndroidWorld benchmark adapter, bootstrap, scoring, and output-dir resume behavior.

Recommended order for the first real smoke run:

1. Launch the AndroidWorld emulator from the command line with `-grpc 8554`.
2. Run `adb devices` and confirm the target serial appears as `device`.
3. Keep `MOBILE_AGENT_V3_5_HOME`, `ANDROID_WORLD_HOME`, and `ANDROID_WORLD_PYTHON` set.
4. Reuse `PHONE_AGENT_*` unless you want Mobile-Agent-v3.5 to use a different endpoint through `MOBILE_AGENT_V3_5_*`.
5. Start with the same config in smoke mode before using its default full-suite mode.

```bash
emulator -avd AndroidWorldAvd -no-snapshot -grpc 8554
adb devices

SNOWL_ANDROIDWORLD_SUITE_FAMILY=android SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend snowl-mobile validate-config configs/runs/mobile_agent_v3_5_androidworld.yml
SNOWL_ANDROIDWORLD_SUITE_FAMILY=android SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend snowl-mobile plan configs/runs/mobile_agent_v3_5_androidworld.yml
SNOWL_ANDROIDWORLD_SUITE_FAMILY=android SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend snowl-mobile run configs/runs/mobile_agent_v3_5_androidworld.yml --device-mode existing_device --adb-serial emulator-5554 --output-dir /tmp/snowl-mobile-mobile-agent-v3-5-androidworld
snowl-mobile summarize /tmp/snowl-mobile-mobile-agent-v3-5-androidworld
```

After the smoke path is stable, switch to the same config without overrides:

```bash
snowl-mobile validate-config configs/runs/mobile_agent_v3_5_androidworld.yml
snowl-mobile plan configs/runs/mobile_agent_v3_5_androidworld.yml
snowl-mobile run configs/runs/mobile_agent_v3_5_androidworld.yml --device-mode existing_device --adb-serial emulator-5554 --output-dir /tmp/snowl-mobile-mobile-agent-v3-5-androidworld-full
snowl-mobile summarize /tmp/snowl-mobile-mobile-agent-v3-5-androidworld-full
```

Look under:

- `/tmp/snowl-mobile-mobile-agent-v3-5-androidworld-full/run.log`
- `/tmp/snowl-mobile-mobile-agent-v3-5-androidworld-full/summary.json`
- `/tmp/snowl-mobile-mobile-agent-v3-5-androidworld-full/trials/<trial_id>/score.json`
- `/tmp/snowl-mobile-mobile-agent-v3-5-androidworld-full/trials/<trial_id>/trajectory.json`
- `/tmp/snowl-mobile-mobile-agent-v3-5-androidworld-full/trials/<trial_id>/raw/mobile_agent_v3_5_androidworld/bridge_request.json`
- `/tmp/snowl-mobile-mobile-agent-v3-5-androidworld-full/trials/<trial_id>/raw/mobile_agent_v3_5_androidworld/final_result.json`
- `/tmp/snowl-mobile-mobile-agent-v3-5-androidworld-full/trials/<trial_id>/raw/mobile_agent_v3_5/runner_result.json`

## 10. Optional: run Mobile-Agent-v3.5 through the same platform flow

This path now uses the dedicated `mobile_agent_v3_5__mobilesafetybench` pair bridge and goes through the normal `validate-config -> plan -> run -> summarize` platform flow.

Recommended order:

1. Start an Android emulator manually.
2. Run `adb devices` and confirm the target serial appears as `device`.
3. Make sure `MOBILE_AGENT_V3_5_HOME` is resolvable, and pass `--model-name`, `--base-url`, and `--api-key` on the CLI if you want to override the checked-in defaults.
4. Make sure `openai`, `pillow`, and `numpy` are installed in the current Python environment.
5. Export a one-task `SNOWL_TASK_SELECTOR` first.
6. Only after the smoke path is stable, unset it and switch to the full-manifest default.

```bash
export SNOWL_TASK_SELECTOR='task_category=text_message_sending,task_id=low_risk_001,limit=1'
snowl-mobile validate-config configs/runs/mobile_agent_v3_5_mobilesafetybench.yml
snowl-mobile plan configs/runs/mobile_agent_v3_5_mobilesafetybench.yml
snowl-mobile run configs/runs/mobile_agent_v3_5_mobilesafetybench.yml --device-mode existing_device --adb-serial emulator-5554 --output-dir /tmp/snowl-mobile-mobile-agent-v3-5-smoke
snowl-mobile summarize /tmp/snowl-mobile-mobile-agent-v3-5-smoke
unset SNOWL_TASK_SELECTOR
```

After the smoke path is stable, switch to the full-manifest config:

```bash
snowl-mobile validate-config configs/runs/mobile_agent_v3_5_mobilesafetybench.yml
snowl-mobile plan configs/runs/mobile_agent_v3_5_mobilesafetybench.yml
snowl-mobile run configs/runs/mobile_agent_v3_5_mobilesafetybench.yml --device-mode existing_device --adb-serial emulator-5554 --output-dir /tmp/snowl-mobile-mobile-agent-v3-5-full
snowl-mobile summarize /tmp/snowl-mobile-mobile-agent-v3-5-full
```

To validate the same pair path without touching a real device:

```bash
export SNOWL_TASK_SELECTOR='task_category=text_message_sending,task_id=low_risk_001,limit=1'
snowl-mobile run configs/runs/mobile_agent_v3_5_mobilesafetybench.yml --device-mode fake --output-dir /tmp/snowl-mobile-mobile-agent-v3-5-fake
unset SNOWL_TASK_SELECTOR
```

Look under:

- `/tmp/snowl-mobile-mobile-agent-v3-5-full/run.log`
- `/tmp/snowl-mobile-mobile-agent-v3-5-full/summary.json`
- `/tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5_mobilesafetybench/bridge_request.json`
- `/tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5_mobilesafetybench/environment_init.console.txt`
- `/tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5_mobilesafetybench/final_result.json`
- `/tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5/request.json`
- `/tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5/runner_request.json`
- `/tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5/runner_result.json`
- `/tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5/wrapped_result.json`
- `/tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5/steps/0001.model_response.json`
- `/tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/trajectory.json`
- `/tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/score.json`
