# snowl-mobile Dynamic Safety Testing Wind Tunnel for Mobile Agents

<div align="center">

<img src="https://cdn-avatars.huggingface.co/v1/production/uploads/61def72b6742e9faa77b0edc/XHPe_wPj4roSniCHsHYT5.jpeg" alt="WhitzardAgent logo" width="120" />

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**WhitzardAgent | Fudan University | Shanghai Innovation Institute (SII)**

[Chinese README](README.zh-CN.md)
</div>

## Overview

`snowl-mobile` is a unified evaluation platform for `Mobile Agent x Benchmark x Model x Emulator`.

It mainly solves these problems:

- running full benchmarks from one CLI or web UI
- supporting multi-emulator parallel scheduling
- resuming interrupted runs with the same `--output-dir`
- stably saving logs, trajectories, screenshots, XML, and scores for every trial
- integrating new agents and benchmarks with low friction

<img src="docs/web_1.png" alt="snowl-mobile" width="888" >
<img src="docs/web_2.png" alt="snowl-mobile" width="888" >

## Current Supported Run Combinations

The repository currently integrates 3 mobile agents and 2 mobile-agent benchmarks, for a total of 6 ready-to-run combinations:

| Agent | Benchmark | Config |
| --- | --- | --- |
| Open-AutoGLM | MobileSafetyBench | `configs/runs/autoglm_mobilesafetybench.yml` |
| Mobile-Agent-E | MobileSafetyBench | `configs/runs/mobile_agent_e_mobilesafetybench.yml` |
| Mobile-Agent-v3.5 | MobileSafetyBench | `configs/runs/mobile_agent_v3_5_mobilesafetybench.yml` |
| Open-AutoGLM | AndroidWorld | `configs/runs/autoglm_androidworld.yml` |
| Mobile-Agent-E | AndroidWorld | `configs/runs/mobile_agent_e_androidworld.yml` |
| Mobile-Agent-v3.5 | AndroidWorld | `configs/runs/mobile_agent_v3_5_androidworld.yml` |

<!-- Another benchmark-only config is also kept in the repository:

- `configs/runs/androidworld_benchmark.yml`
-->

## What You Need Before Running

- Python `>= 3.11`
- Android SDK and `adb`
- Appium
- at least one already-started Android emulator
- an OpenAI-compatible model service endpoint

Several important notes:

- MobileSafetyBench depends on Appium.
- MobileSafetyBench also requires the emulator to have a `test_env_100` snapshot created before the run.
- It is recommended to read the MobileSafetyBench README for more details: https://github.com/jylee425/mobilesafetybench
- AndroidWorld is better run in a separate Python environment and referenced through `ANDROID_WORLD_PYTHON`.
- AndroidWorld emulators are recommended to use Android 13 / API 33 and be started from the command line with `-grpc`.
- It is recommended to read the AndroidWorld README for more details: https://github.com/google-research/android_world
- If you want parallel runs, pass one `--adb-serial` for each emulator and set `--batch-size` to the number of workers you want.

## First-Time Setup: Full Walkthrough

### 1. Clone this repository

```bash
git clone <your-snowl-mobile-repo-url>
cd snowl-mobile
```

### 2. Install the platform

Using `venv`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
```

Using `conda`:

```bash
conda create -n snowl-mobile python=3.11 -y
conda activate snowl-mobile
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
```

### 3. Clone the upstream repositories into `references/`

> AutoGLM, Mobile-Agent-E, Mobile-Agent-v3.5, MobileSafetyBench, and AndroidWorld have already been cloned under `references/` in this repository setup, so you do not need to clone them again.

Expected layout:

```text
references/agents/Open-AutoGLM/
references/agents/MobileAgent/Mobile-Agent-E/
references/agents/MobileAgent/Mobile-Agent-v3.5/
references/benchmarks/android_world/
references/benchmarks/mobilesafetybench/
```

For example:

```bash
git clone <Open-AutoGLM-url> references/agents/Open-AutoGLM
git clone <MobileAgent-url> references/agents/MobileAgent/Mobile-Agent-E
git clone <MobileAgent-url> references/agents/MobileAgent/Mobile-Agent-v3.5
git clone <AndroidWorld-url> references/benchmarks/android_world
git clone <MobileSafetyBench-url> references/benchmarks/mobilesafetybench
```

### 4. Install upstream dependencies

Install the dependencies required by the paths you want to run into the current environment:

```bash
python -m pip install -r references/agents/Open-AutoGLM/requirements.txt
python -m pip install -r references/benchmarks/mobilesafetybench/requirements.txt
python -m pip install -r references/agents/MobileAgent/Mobile-Agent-E/requirements.txt
python -m pip install -r references/benchmarks/android_world/requirements.txt
python -m pip install openai pillow numpy
```

<!-- If you want to run AndroidWorld, it is recommended to prepare a separate environment:

```bash
python3 -m venv .venvs/androidworld
.venvs/androidworld/bin/python -m pip install --upgrade pip setuptools wheel
.venvs/androidworld/bin/python -m pip install -r references/benchmarks/android_world/requirements.txt
export ANDROID_WORLD_PYTHON="$PWD/.venvs/androidworld/bin/python"
```
-->

### 5. Start your emulators

For MobileSafetyBench, as long as the emulator is already running and visible in `adb devices`, you can use `existing_device` mode.

For AndroidWorld, it is recommended to start the emulator from the command line with gRPC enabled, for example:

```bash
emulator -avd AndroidWorldAvd -no-snapshot -grpc 8554
```

If you want parallel AndroidWorld runs, each AVD must use a different gRPC port. The CLI still selects devices through `--adb-serial`; `snowl-mobile` derives the emulator console port from the serial and automatically discovers the matching `-grpc` port from the running emulator process.

```bash
emulator -avd AndroidWorldAvd -no-snapshot -grpc 8554
emulator -avd AndroidWorldAvd2 -no-snapshot -grpc 8555
```

Check devices:

```bash
adb devices
```

If you want the platform to do a quick device check first:

```bash
snowl-mobile devices list --config configs/runs/autoglm_mobilesafetybench.yml --device-mode existing_device
snowl-mobile devices health-check --config configs/runs/autoglm_mobilesafetybench.yml --device-mode existing_device
snowl-mobile registry list-agents
snowl-mobile registry list-benchmarks
```

### 6. Install web UI dependencies

```bash
cd mobile-agent-eval-ui
npm install
cd ..
```

### 7. Start the web UI

Before starting the UI backend, keep the same Python environment that you used to install `snowl-mobile` activated. The page backend calls the `snowl-mobile` CLI from the current shell environment.

Optional check:

```bash
which snowl-mobile
```

Start the backend and frontend in two terminals:

Terminal A:

```bash
cd mobile-agent-eval-ui
npm run server
```

Terminal B:

```bash
cd mobile-agent-eval-ui
npm run client
```

Then open:

- Web UI: `http://localhost:5173`
<!-- - Backend API: `http://localhost:8787` -->

### 8. Start your first test from the page

After the page opens, follow these steps:

1. Create one evaluation unit.
2. Choose an `Agent` and a `Benchmark`, for example `AutoGLM` + `MobileSafetyBench`.
3. Fill in `Base URL`, `API Key`, and `Model Name`.
4. For the first run, set `batch_size=1`, `max_steps=20`, and use a new `output_dir`.
5. In the emulator slot, select one AVD and click `Start Emulator`, or make sure an existing emulator already appears in `adb devices`.
6. Wait until the slot becomes ready, then click `Start Evaluation`.
7. Watch the run and result in the unit's `terminal`, `logs`, and `summary` tabs.

Run results are written to `results/<resolved_output_dir>/`. If you reuse the same `output_dir`, the system resumes the previous run instead of starting from scratch.

If you only want the frontend-specific guide, continue with [mobile-agent-eval-ui/README.md](mobile-agent-eval-ui/README.md).

## First Real Backend CLI Run: Open-AutoGLM x MobileSafetyBench

For the first real device-backed run, it is recommended to start with the Open-AutoGLM x MobileSafetyBench command below, set `--batch-size` to `1`, and pass only one emulator. After the artifacts look correct, add more `--adb-serial` values for parallel runs.

## Six Full Evaluation Commands

This is the part most users actually need.

Replace these placeholders:

- `<model-name>`
- `<base-url>`
- `<api-key>`

If you only have one emulator, set `--batch-size` to `1` and pass only one `--adb-serial`.

### MobileSafetyBench

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

### AndroidWorld

Before running AndroidWorld, make sure `ANDROID_WORLD_PYTHON` points to a working AndroidWorld environment.

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

## Optional Fake Test

If you only want to validate the main platform path without touching a real device, you can keep this fake example:

```bash
export SNOWL_TASK_SELECTOR='task_category=text_message_sending,task_id=low_risk_001,limit=1'
snowl-mobile run configs/runs/mobile_agent_v3_5_mobilesafetybench.yml \
  --device-mode fake \
  --output-dir ./tmp/snowl-mobile-mobile-agent-v3-5-fake
unset SNOWL_TASK_SELECTOR
```

## Results, Logs, and Resume

The most commonly used result files are:

- `<run_dir>/run.log`
- `<run_dir>/summary.json`
- `<run_dir>/events.jsonl`
- `<run_dir>/trials/<trial_id>/trial.log`
- `<run_dir>/trials/<trial_id>/score.json`
- `<run_dir>/trials/<trial_id>/trajectory.json`

Useful commands:

```bash
tail -f <run_dir>/run.log
snowl-mobile summarize <run_dir>
```

Resume rules:

- rerun the same command
- reuse the same `--output-dir`
- completed trials are skipped
- failed or incomplete trials continue running

Parallel scheduling rules:

- `snowl-mobile run` occupies multiple emulators at the same time according to `--batch-size`
- as soon as one emulator becomes free, the scheduler immediately fills it with the next queued task

## Manual Integration and Codex-Assisted Integration

`snowl-mobile` is not limited to the 6 run combinations already provided in this repository. You can also integrate new mobile agents and benchmarks yourself.

Recommended workflow:

1. Clone the upstream repository into the expected path under `references/`
2. Ask Codex to follow the repository integration prompts and docs, or complete the integration manually
3. Register the new adapter or bridge and add a new run config
4. Keep using the same `snowl-mobile run ...` entrypoint afterward

Recommended clone paths:

- new agent repository: `references/agents/<repo_name>/`
- new benchmark repository: `references/benchmarks/<repo_name>/`

If you want Codex to help with the integration, you can directly use these documents:

- Agent integration guide: [docs/integrate-agent.md](docs/integrate-agent.md)
- Benchmark integration guide: [docs/integrate-benchmark.md](docs/integrate-benchmark.md)
- Pair or bridge integration guide: [docs/integrate-pair.md](docs/integrate-pair.md)
- Codex prompt for agent integration: [docs/prompts/integrate-agent-prompt.md](docs/prompts/integrate-agent-prompt.md)
- Codex prompt for benchmark integration: [docs/prompts/integrate-benchmark-prompt.md](docs/prompts/integrate-benchmark-prompt.md)

If you want to analyze a newly cloned repository before deciding how to integrate it, you can start with:

```bash
PYTHONPATH=src python3 -m snowl_mobile inspect-repo agent references/agents/<repo_name>
PYTHONPATH=src python3 -m snowl_mobile inspect-repo benchmark references/benchmarks/<repo_name>
PYTHONPATH=src python3 -m snowl_mobile integration-checklist agent references/agents/<repo_name>
PYTHONPATH=src python3 -m snowl_mobile integration-checklist benchmark references/benchmarks/<repo_name>
```

## More Documentation

- Quickstart: [docs/quickstart.md](docs/quickstart.md)
- Troubleshooting: [docs/troubleshooting.md](docs/troubleshooting.md)
- AndroidWorld notes: [docs/integrations/androidworld.md](docs/integrations/androidworld.md)
- Open-AutoGLM notes: [docs/integrations/open-autoglm.md](docs/integrations/open-autoglm.md)
- Mobile-Agent-E notes: [docs/integrations/mobile-agent-e.md](docs/integrations/mobile-agent-e.md)
- Mobile-Agent-v3.5 notes: [docs/integrations/mobile-agent-v3-5.md](docs/integrations/mobile-agent-v3-5.md)
- MobileSafetyBench notes: [docs/integrations/mobilesafetybench.md](docs/integrations/mobilesafetybench.md)
- Open-AutoGLM x MobileSafetyBench bridge notes: [docs/integrations/open-autoglm-mobilesafetybench.md](docs/integrations/open-autoglm-mobilesafetybench.md)

## License

This project is licensed under the **MIT License**. See [LICENSE](LICENSE) for details.
