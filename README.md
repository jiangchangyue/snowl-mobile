# snowl-mobile 终端智能体动态安全测试风洞

[Chinese README](README.zh-CN.md)

`snowl-mobile` is a platform for running `Mobile Agent x Benchmark x Model x Emulator` evaluations with one CLI.

It is designed for:

- running full benchmark suites instead of one-off demos
- scheduling trials across multiple Android emulators
- resuming interrupted runs by reusing the same `--output-dir`
- saving logs, trajectories, screenshots, XML, and scores for every trial
- integrating new agents and benchmarks without rewriting the platform core

## Supported Runs

The repository currently ships 6 checked-in full-run configs:

| Agent | Benchmark | Config |
| --- | --- | --- |
| Open-AutoGLM | MobileSafetyBench | `configs/runs/autoglm_mobilesafetybench.yml` |
| Mobile-Agent-E | MobileSafetyBench | `configs/runs/mobile_agent_e_mobilesafetybench.yml` |
| Mobile-Agent-v3.5 | MobileSafetyBench | `configs/runs/mobile_agent_v3_5_mobilesafetybench.yml` |
| Open-AutoGLM | AndroidWorld | `configs/runs/autoglm_androidworld.yml` |
| Mobile-Agent-E | AndroidWorld | `configs/runs/mobile_agent_e_androidworld.yml` |
| Mobile-Agent-v3.5 | AndroidWorld | `configs/runs/mobile_agent_v3_5_androidworld.yml` |

There is also one benchmark-only config:

- `configs/runs/androidworld_benchmark.yml`

## What You Need

- Python `>= 3.11`
- Node.js `>= 18` and `npm` if you want to use the web UI
- Android SDK and `adb`
- Appium for MobileSafetyBench runs
- at least one running Android emulator
- access to an OpenAI-compatible model endpoint

Important runtime notes:

- MobileSafetyBench runs need Appium.
- AndroidWorld runs work best with a dedicated Python environment exposed through `ANDROID_WORLD_PYTHON`.
- AndroidWorld emulators should be Android 13 / API 33 and started from the command line with gRPC enabled.
- For parallel runs, pass one `--adb-serial` per emulator and set `--batch-size` to the number of worker slots you want.

## First-Time Setup

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

### 3. Clone the upstream repos under `references/`

Expected paths:

```text
references/agents/Open-AutoGLM/
references/agents/MobileAgent/Mobile-Agent-E/
references/agents/MobileAgent/Mobile-Agent-v3.5/
references/benchmarks/android_world/
references/benchmarks/mobilesafetybench/
```

Example:

```bash
git clone <Open-AutoGLM-url> references/agents/Open-AutoGLM
git clone <MobileAgent-url> references/agents/MobileAgent/Mobile-Agent-E
git clone <MobileAgent-url> references/agents/MobileAgent/Mobile-Agent-v3.5
git clone <AndroidWorld-url> references/benchmarks/android_world
git clone <MobileSafetyBench-url> references/benchmarks/mobilesafetybench
```

### 4. Install upstream dependencies

Install the dependencies needed by the paths you want to run:

```bash
python -m pip install -r references/agents/Open-AutoGLM/requirements.txt
python -m pip install -r references/benchmarks/mobilesafetybench/requirements.txt
python -m pip install -r references/agents/MobileAgent/Mobile-Agent-E/requirements.txt
python -m pip install openai pillow numpy
```

For AndroidWorld, a dedicated environment is recommended:

```bash
python3 -m venv .venvs/androidworld
.venvs/androidworld/bin/python -m pip install --upgrade pip setuptools wheel
.venvs/androidworld/bin/python -m pip install -r references/benchmarks/android_world/requirements.txt
export ANDROID_WORLD_PYTHON="$PWD/.venvs/androidworld/bin/python"
```

### 5. Start your emulators

For MobileSafetyBench, any already-running emulator visible in `adb devices` can be used with `existing_device`.

For AndroidWorld, start the emulator from the command line with gRPC enabled, for example:

```bash
emulator -avd AndroidWorldAvd -no-snapshot -grpc 8554
```

For AndroidWorld parallel runs, start every AVD with a unique gRPC port. The CLI still selects devices by `--adb-serial`; `snowl-mobile` resolves the emulator console port from that serial and discovers the matching `-grpc` port from the running emulator process.

```bash
emulator -avd AndroidWorldAvd -no-snapshot -grpc 8554
emulator -avd AndroidWorldAvd2 -no-snapshot -grpc 8555
```

Check that your devices are visible:

```bash
adb devices
```

Optional platform-side checks:

```bash
snowl-mobile devices list --config configs/runs/autoglm_mobilesafetybench.yml --device-mode existing_device
snowl-mobile devices health-check --config configs/runs/autoglm_mobilesafetybench.yml --device-mode existing_device
snowl-mobile registry list-agents
snowl-mobile registry list-benchmarks
```

### 6. Install the web UI dependencies

```bash
cd mobile-agent-eval-ui
npm install
cd ..
```

### 7. Start the web UI

Keep the same Python environment active when starting the UI backend. The UI server launches the `snowl-mobile` CLI from the current shell environment.

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

- frontend: `http://localhost:5173`
<!-- - backend API: `http://localhost:8787` -->

### 8. Start your first test from the page

After the page opens:

1. Add one evaluation unit.
2. Choose an `Agent` and a `Benchmark`, for example `AutoGLM` + `MobileSafetyBench`.
3. Fill in `Base URL`, `API Key`, and `Model Name`.
4. Set `batch_size=1`, choose a fresh `output_dir`, and keep `max_steps=20` for the first run.
5. In the emulator slot, select an AVD and click `Start Emulator`, or make sure an already-running emulator is visible in `adb devices`.
6. Wait until the slot becomes ready, then click `Start Evaluation`.
7. Watch progress in the unit's `terminal`, `logs`, and `summary` tabs.

Results are written under `results/<resolved_output_dir>/`. Reusing the same `output_dir` resumes an interrupted run instead of starting a brand-new one.

For UI-only details, see [mobile-agent-eval-ui/README.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/mobile-agent-eval-ui/README.md).

## First Real Run: Open-AutoGLM x MobileSafetyBench

For the first real device-backed run, use the Open-AutoGLM x MobileSafetyBench command below with one running emulator and `--batch-size 1`, then scale to multiple `--adb-serial` values after the artifacts look healthy.

## Full Evaluation Commands

These are the main commands most users need.

Replace:

- `<model-name>`
- `<base-url>`
- `<api-key>`

If you only have one emulator, set `--batch-size 1` and pass only one `--adb-serial`.

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

Before AndroidWorld runs, make sure `ANDROID_WORLD_PYTHON` points to a working AndroidWorld environment.

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

If you only want to validate the platform path without touching a real device, keep this one fake example:

```bash
export SNOWL_TASK_SELECTOR='task_category=text_message_sending,task_id=low_risk_001,limit=1'
snowl-mobile run configs/runs/mobile_agent_v3_5_mobilesafetybench.yml \
  --device-mode fake \
  --output-dir ./tmp/snowl-mobile-mobile-agent-v3-5-fake
unset SNOWL_TASK_SELECTOR
```

## Results, Logs, and Resume

During a run, the most useful files are:

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

Resume behavior:

- rerun the same command with the same `--output-dir`
- completed trials are reused
- failed or incomplete trials are scheduled again

Parallel scheduling behavior:

- `snowl-mobile run` starts tasks on as many emulators as allowed by `--batch-size`
- when one emulator becomes idle, the next queued task is scheduled onto it automatically

## Manual And Codex-Assisted Integration Workflows

`snowl-mobile` is not limited to the 6 checked-in runs above. Users can also integrate their own mobile agents and benchmarks.

Recommended workflow:

1. Clone the upstream repository into the expected local path under `references/`
2. Ask Codex to integrate it by following the repository's integration prompt/docs, or follow the manual integration docs yourself
3. Register the new adapter/bridge and add a run config
4. Run the new pair through the same `snowl-mobile run ...` entrypoint

Expected clone locations:

- new agent repos: `references/agents/<repo_name>/`
- new benchmark repos: `references/benchmarks/<repo_name>/`

If you want Codex to do the integration work, point it to:

- agent integration guide: [docs/integrate-agent.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/integrate-agent.md)
- benchmark integration guide: [docs/integrate-benchmark.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/integrate-benchmark.md)
- pair/bridge integration guide: [docs/integrate-pair.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/integrate-pair.md)
- Codex prompt for new agents: [docs/prompts/integrate-agent-prompt.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/prompts/integrate-agent-prompt.md)
- Codex prompt for new benchmarks: [docs/prompts/integrate-benchmark-prompt.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/prompts/integrate-benchmark-prompt.md)

If you want to inspect a newly cloned repo before integrating it, the platform also provides:

```bash
PYTHONPATH=src python3 -m snowl_mobile inspect-repo agent references/agents/<repo_name>
PYTHONPATH=src python3 -m snowl_mobile inspect-repo benchmark references/benchmarks/<repo_name>
PYTHONPATH=src python3 -m snowl_mobile integration-checklist agent references/agents/<repo_name>
PYTHONPATH=src python3 -m snowl_mobile integration-checklist benchmark references/benchmarks/<repo_name>
```

## More Documentation

- Quickstart: [docs/quickstart.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/quickstart.md)
- Troubleshooting: [docs/troubleshooting.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/troubleshooting.md)
- Integration readiness checklist: [docs/integration-readiness-checklist.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/integration-readiness-checklist.md)
- AndroidWorld notes: [docs/integrations/androidworld.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/integrations/androidworld.md)
- Open-AutoGLM notes: [docs/integrations/open-autoglm.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/integrations/open-autoglm.md)
- Mobile-Agent-E notes: [docs/integrations/mobile-agent-e.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/integrations/mobile-agent-e.md)
- Mobile-Agent-v3.5 notes: [docs/integrations/mobile-agent-v3-5.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/integrations/mobile-agent-v3-5.md)
- MobileSafetyBench notes: [docs/integrations/mobilesafetybench.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/integrations/mobilesafetybench.md)
- Open-AutoGLM x MobileSafetyBench bridge notes: [docs/integrations/open-autoglm-mobilesafetybench.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/integrations/open-autoglm-mobilesafetybench.md)

## License

MIT
