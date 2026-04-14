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

The CLI no longer auto-loads `.env` or `.env.local`, and the repository no longer keeps checked-in `.env.*` templates.

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
snowl-mobile run configs/runs/autoglm_mobilesafetybench.yml \
  --model-name Qwen2.5-VL-72B-Instruct \
  --base-url https://your-openai-compatible-endpoint/v1 \
  --api-key '<your-api-key>' \
  --max-steps 20 \
  --batch-size 3 \
  --device-mode existing_device \
  --adb-serial emulator-5556 \
  --adb-serial emulator-5558 \
  --adb-serial emulator-5560 \
  --output-dir ./tmp/snowl-mobile-autoglm-mobilesafetybench
snowl-mobile summarize ./tmp/snowl-mobile-autoglm-mobilesafetybench
```

`--output-dir` is the run directory itself. Reusing the same path resumes the run automatically, reuses completed/skipped trials, and reruns failed or partial ones.

This checked-in config now defaults to the full MobileSafetyBench task set, and the repository documentation now treats the direct full-run command as the canonical workflow.

To keep multiple existing emulators busy in parallel and automatically refill whichever one finishes first:

For a two-emulator smoke test, use `--batch-size 2` and pass two `--adb-serial` values.

```bash
snowl-mobile run configs/runs/autoglm_mobilesafetybench.yml \
  --model-name Qwen2.5-VL-72B-Instruct \
  --base-url https://your-openai-compatible-endpoint/v1 \
  --api-key '<your-api-key>' \
  --max-steps 20 \
  --batch-size 3 \
  --device-mode existing_device \
  --adb-serial emulator-5556 \
  --adb-serial emulator-5558 \
  --adb-serial emulator-5560 \
  --output-dir ./tmp/snowl-mobile-autoglm-mobilesafetybench
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

## 8c. Canonical full-run commands

The current user-facing workflow is now the same across all six checked-in pair configs: run the full task set directly from the canonical config, pass model/runtime settings on the CLI, pass one `--adb-serial` per live emulator, and reuse the same `--output-dir` to resume.

Open-AutoGLM x MobileSafetyBench:

```bash
snowl-mobile run configs/runs/autoglm_mobilesafetybench.yml \
  --model-name <model-name> \
  --base-url <base-url> \
  --api-key '<api-key>' \
  --max-steps 20 \
  --batch-size 3 \
  --device-mode existing_device \
  --adb-serial emulator-5556 \
  --adb-serial emulator-5558 \
  --adb-serial emulator-5560 \
  --output-dir ./tmp/snowl-mobile-autoglm-mobilesafetybench
```

Open-AutoGLM x AndroidWorld:

```bash
snowl-mobile run configs/runs/autoglm_androidworld.yml \
  --model-name <model-name> \
  --base-url <base-url> \
  --api-key '<api-key>' \
  --max-steps 20 \
  --batch-size 3 \
  --device-mode existing_device \
  --adb-serial emulator-5556 \
  --adb-serial emulator-5558 \
  --adb-serial emulator-5560 \
  --output-dir ./tmp/snowl-mobile-open-autoglm-androidworld
```

Mobile-Agent-E x MobileSafetyBench:

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

Mobile-Agent-E x AndroidWorld:

```bash
snowl-mobile run configs/runs/mobile_agent_e_androidworld.yml \
  --model-name <model-name> \
  --base-url <base-url> \
  --api-key '<api-key>' \
  --max-steps 20 \
  --batch-size 3 \
  --device-mode existing_device \
  --adb-serial emulator-5556 \
  --adb-serial emulator-5558 \
  --adb-serial emulator-5560 \
  --output-dir ./tmp/snowl-mobile-mobile-agent-e-androidworld
```

Mobile-Agent-v3.5 x MobileSafetyBench:

```bash
snowl-mobile run configs/runs/mobile_agent_v3_5_mobilesafetybench.yml \
  --model-name <model-name> \
  --base-url <base-url> \
  --api-key '<api-key>' \
  --max-steps 20 \
  --batch-size 3 \
  --device-mode existing_device \
  --adb-serial emulator-5556 \
  --adb-serial emulator-5558 \
  --adb-serial emulator-5560 \
  --output-dir ./tmp/snowl-mobile-mobile-agent-v3-5-mobilesafetybench
```

Mobile-Agent-v3.5 x AndroidWorld:

```bash
snowl-mobile run configs/runs/mobile_agent_v3_5_androidworld.yml \
  --model-name <model-name> \
  --base-url <base-url> \
  --api-key '<api-key>' \
  --max-steps 20 \
  --batch-size 3 \
  --device-mode existing_device \
  --adb-serial emulator-5556 \
  --adb-serial emulator-5558 \
  --adb-serial emulator-5560 \
  --output-dir ./tmp/snowl-mobile-mobile-agent-v3-5-androidworld
```

## 9. Optional platform-only fake test

To validate the same pair path without touching a real device:

```bash
export SNOWL_TASK_SELECTOR='task_category=text_message_sending,task_id=low_risk_001,limit=1'
snowl-mobile run configs/runs/mobile_agent_v3_5_mobilesafetybench.yml \
  --device-mode fake \
  --output-dir ./tmp/snowl-mobile-mobile-agent-v3-5-fake
unset SNOWL_TASK_SELECTOR
```

Look under:

- `./tmp/snowl-mobile-mobile-agent-v3-5-fake/run.log`
- `./tmp/snowl-mobile-mobile-agent-v3-5-fake/summary.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-fake/trials/<trial_id>/raw/mobile_agent_v3_5_mobilesafetybench/bridge_request.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-fake/trials/<trial_id>/raw/mobile_agent_v3_5_mobilesafetybench/environment_init.console.txt`
- `./tmp/snowl-mobile-mobile-agent-v3-5-fake/trials/<trial_id>/raw/mobile_agent_v3_5_mobilesafetybench/final_result.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-fake/trials/<trial_id>/raw/mobile_agent_v3_5/request.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-fake/trials/<trial_id>/raw/mobile_agent_v3_5/runner_request.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-fake/trials/<trial_id>/raw/mobile_agent_v3_5/runner_result.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-fake/trials/<trial_id>/raw/mobile_agent_v3_5/wrapped_result.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-fake/trials/<trial_id>/raw/mobile_agent_v3_5/steps/0001.model_response.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-fake/trials/<trial_id>/trajectory.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-fake/trials/<trial_id>/score.json`
