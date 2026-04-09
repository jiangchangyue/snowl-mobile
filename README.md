# snowl-mobile

[Chinese README](README.zh-CN.md)

snowl-mobile is a platform-oriented evaluation framework for Mobile Agent x Benchmark x Model x Emulator runs.

Current repository status, stated plainly:

- The platform core is in place: config loading, contracts, registry, planning, scheduler skeleton, artifacts, devices, integration toolkit, and CLI.
- `mobilesafetybench` is integrated as the first real benchmark adapter.
- `androidworld` is now registered as a real benchmark adapter with benchmark-side `validate-config -> plan -> benchmark-setup -> benchmark-run` support.
- `open_autoglm` is integrated as the first real agent adapter.
- `mobile_agent_e` is now registered as a second real-agent adapter and can be executed by the platform through a wrap-first subprocess path.
- `mobile_agent_v3_5` is now registered as a third real-agent adapter and now also has a dedicated `mobile_agent_v3_5__mobilesafetybench` pair bridge for the first real MobileSafetyBench closure.
- `open_autoglm x mobilesafetybench` is the first real pair wired into the unified `validate-config -> plan -> run -> summarize` flow.
- `open_autoglm x androidworld` now also has a first minimal real pair bridge, focused on one-device, tiny-subset validation rather than full-suite throughput.
- `mobile_agent_e x mobilesafetybench` now also has a dedicated pair bridge, so MobileSafetyBench reset/seed runs before the Mobile-Agent-E subprocess starts.
- `mobile_agent_e x androidworld` now also has a dedicated pair bridge, reusing the same AndroidWorld benchmark adapter, runtime recipe pattern, and artifact layout as the Open-AutoGLM path.
- `mobile_agent_v3_5 x androidworld` now also has a dedicated pair bridge, reusing the same AndroidWorld benchmark/bootstrap/scoring path while keeping Mobile-Agent-v3.5's own wrapped runner in control of actions.
- The checked-in pair configs now support CLI-driven model/runtime overrides and true multi-emulator scheduling for `run` when `--batch-size > 1` and multiple `--adb-serial` values are provided.

This means the project is already usable for a first real closure, but it is not yet a fully generic production runner for arbitrary third-party agents and benchmarks.

## What Works Today

- `validate-config`, `plan`, `run`, `summarize`
- builtin registry discovery for agents, benchmarks, and bridges
- wrap-first Mobile-Agent-E adapter registration, compatibility checks, dry-run coverage, and platform-driven wrapped execution
- wrap-first Mobile-Agent-v3.5 adapter registration, compatibility checks, config loading, dry-run coverage, and platform-driven wrapped execution
- dedicated `mobile_agent_e__mobilesafetybench` pair bridge with MobileSafetyBench environment bootstrap and pair-level raw artifacts
- dedicated `mobile_agent_v3_5__mobilesafetybench` pair bridge with MobileSafetyBench environment bootstrap, bridge-level observations, and final-state evaluation
- AndroidWorld benchmark registration with upstream-backed task discovery, benchmark-side runtime probe support, and checked-in configs:
  - `configs/integrations/androidworld/minimal.yml`
  - `configs/runs/androidworld_benchmark.yml`
- first AndroidWorld real-pair config:
  - `configs/runs/autoglm_androidworld.yml`
- canonical Mobile-Agent-E AndroidWorld real-pair config:
  - `configs/runs/mobile_agent_e_androidworld.yml`
- canonical Mobile-Agent-v3.5 AndroidWorld real-pair config:
  - `configs/runs/mobile_agent_v3_5_androidworld.yml`
- `devices list` and `devices health-check`
- fake-device dry runs and dummy end-to-end runs
- real Android emulator discovery through `adb` in `existing_device` mode
- first real pair config:
  - `configs/runs/autoglm_mobilesafetybench.yml`
- run artifacts:
  - `manifest.json`
  - `plan.json`
  - `summary.json`
  - `events.jsonl`
  - per-trial `meta.json`, `score.json`, `trajectory.json`, `trial.log`, `steps/`

## Honest Limits

- The real pair path is `in_process`, so the Python environment running `snowl-mobile run` must also be able to import both upstream repos and their dependencies.
- `mobile_agent_e` still has no platform-created dedicated worker env. The AndroidWorld pair bridge can point at `ANDROID_WORLD_PYTHON`, but the platform does not create or manage that interpreter for you yet.
- `mobile_agent_v3_5` now has a checked-in real pair config and pair bridge, but it still has no dedicated worker env.
- `mobile_agent_v3_5` still executes its own ADB loop outside `MobileSafetyEnv.step()`, so evaluator progress is currently reconciled at bootstrap/final-state boundaries instead of full step-by-step native updates.
- the current Mobile-Agent-v3.5 wrapper is intentionally faithful to upstream decisions: the platform binds the device, translates execution prerequisites, and streams artifacts, but it does not rewrite the agent's chosen actions into benchmark-specific fallback actions.
- `open_autoglm x androidworld` now uses the same canonical-config pattern as the other AndroidWorld pair paths: `configs/runs/autoglm_androidworld.yml` defaults to the current full suite, while smoke runs are selected through environment overrides such as `SNOWL_ANDROIDWORLD_SUITE_FAMILY=android` and `SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend`.
- a real full-suite `open_autoglm x androidworld` run is still gated on having one Python interpreter that can import both AndroidWorld and Open-AutoGLM upstream dependencies.
- `mobile_agent_e x androidworld` is now wired through the same AndroidWorld benchmark/bootstrap/scoring path, but it is still a first minimal pair bridge and has not been fully validated as a real full-suite run in this workspace.
- `configs/runs/mobile_agent_e_androidworld.yml` is the canonical checked-in config for both smoke and full-suite AndroidWorld runs. It defaults to the full `android_world` family, and smoke runs are selected through environment overrides such as `SNOWL_ANDROIDWORLD_SUITE_FAMILY=android` and `SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend`.
- `mobile_agent_v3_5 x androidworld` is now wired through the same AndroidWorld benchmark/bootstrap/scoring path, but a real long-run/full-suite verification is still pending in this workspace.
- `configs/runs/mobile_agent_v3_5_androidworld.yml` is the canonical checked-in config for both smoke and full-suite AndroidWorld runs. It defaults to the full `android_world` family, and smoke runs are selected through environment overrides such as `SNOWL_ANDROIDWORLD_SUITE_FAMILY=android` and `SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend`.
- `existing_device` is the practical path for the first real run. `managed_avd` is not complete yet.
- Pair runs can now keep multiple leased emulators busy in the same `run` invocation, but the in-process bridge architecture still shares one host Python environment and benchmark-side `benchmark-run` remains a simpler path.
- AndroidWorld full runs now support the same output-dir resume flow as the rest of the platform: rerun the same command with the same `--output-dir` and previously completed/skipped trials are reused automatically, while failed/aborted trials are cleared and run again. This is artifact-level resume, not in-trial step checkpoint resume.
- Automatic recovery for Appium, upstream runtime, and model endpoint failures is still limited.
- If you previously exported `MOBILE_AGENT_E_LIGHTWEIGHT_PERCEPTION=1` in your shell, removing it from a config file does not unset the current shell variable; run `unset MOBILE_AGENT_E_LIGHTWEIGHT_PERCEPTION` before testing the full perception path.

## Requirements

For the platform itself:

- Python `>= 3.11`
- `pip`

For the first real pair (`Open-AutoGLM x MobileSafetyBench`):

- Android Studio / Android SDK
- `adb` available in `PATH`
- at least one Android emulator started manually by the user
- Appium installed and callable
- a reachable OpenAI-compatible model endpoint for Open-AutoGLM

## First-Time Setup

### 1. Clone this repository

```bash
git clone <your-snowl-mobile-repo-url>
cd snowl-mobile
```

### 2. Create a virtual environment

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

Conda environment management:

```bash
conda deactivate
conda env remove -n snowl-mobile
```

After installation, you can use either:

- `snowl-mobile ...`
- `python -m snowl_mobile ...`

If you do not install the package, use:

```bash
PYTHONPATH=src python3 -m snowl_mobile ...
```

If `pip install -e .` fails in a minimal or offline environment because the build backend is unavailable, keep working from source with `PYTHONPATH=src` and see `docs/troubleshooting.md`.

### 3. Put third-party repos under `references/`

These repos are not cloned automatically. You must clone them manually:

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
git clone <MobileAgent-url> references/agents/MobileAgent/Mobile-Agent-v3.5
git clone <MobileSafetyBench-url> references/benchmarks/mobilesafetybench
```

### 4. Install upstream dependencies for the real paths you want to use

Because the current real execution paths still share the host environment, install the upstream Python dependencies into the same environment that runs `snowl-mobile`:

```bash
python -m pip install -r references/agents/Open-AutoGLM/requirements.txt
python -m pip install -r references/benchmarks/mobilesafetybench/requirements.txt
python -m pip install -r references/agents/MobileAgent/Mobile-Agent-E/requirements.txt
python -m pip install openai pillow numpy
```

If you want to use AndroidWorld through the platform today, also clone `references/benchmarks/android_world`. The benchmark now supports `validate-config / plan / benchmark-setup / benchmark-run`, and the checked-in pair configs are `configs/runs/autoglm_androidworld.yml`, `configs/runs/mobile_agent_e_androidworld.yml`, and `configs/runs/mobile_agent_v3_5_androidworld.yml`. A dedicated AndroidWorld Python environment is still recommended instead of forcing its dependencies into the main run environment. Point `ANDROID_WORLD_PYTHON` at that environment when possible.

### 5. Configure runtime inputs

The CLI no longer auto-loads `.env` or `.env.local`.

The platform now auto-resolves these from the repository or local `PATH` when possible:

- `OPEN_AUTOGLM_HOME`
- `MOBILE_AGENT_E_HOME`
- `MOBILE_AGENT_V3_5_HOME`
- `MOBILE_SAFETY_HOME`
- `ANDROID_WORLD_HOME`
- `APPIUM_BIN` if `appium` is already on `PATH`

The values you still need to provide at run time are mainly model endpoint settings and any local Android/AndroidWorld interpreter paths:

- `PHONE_AGENT_BASE_URL`
- `PHONE_AGENT_API_KEY`
- `PHONE_AGENT_MODEL` or `--model-name`
- `ANDROID_WORLD_PYTHON` if AndroidWorld dependencies live in a dedicated virtualenv
- `ANDROID_SDK_ROOT`

Recommended options:

- pass `--model-name`, `--base-url`, `--api-key`, `--max-steps`, and `--batch-size` directly to `snowl-mobile run`
- or export the equivalent `PHONE_AGENT_*` / `ANDROID_WORLD_*` shell variables yourself before running

Notes:

- `provider`, `api_style`, and modalities still live in the run config under `models:`.
- the checked-in run configs default to safe model names, but runtime CLI flags now override them cleanly for one-off runs.
- `PHONE_AGENT_MODEL` remains the fallback model selector used by the checked-in configs when `--model-name` is omitted.
- Mobile-Agent-E's wrap-first adapter also declares wrapper-side env slots for later real execution:
- the current wrapped path automatically falls back to `PHONE_AGENT_BASE_URL`, `PHONE_AGENT_API_KEY`, and `PHONE_AGENT_MODEL` if the Mobile-Agent-E-specific reasoning vars are empty.
- Mobile-Agent-E-specific override envs are:
  - `MOBILE_AGENT_E_HOME`
  - `MOBILE_AGENT_E_API_KEY`
  - `MOBILE_AGENT_E_BASE_URL`
  - `MOBILE_AGENT_E_REASONING_MODEL`
  - `MOBILE_AGENT_E_CAPTION_API_KEY`
  - `MOBILE_AGENT_E_CAPTION_BASE_URL`
  - `MOBILE_AGENT_E_CAPTION_MODEL`
  - `MOBILE_AGENT_E_CAPTION_CALL_METHOD`
  - `MOBILE_AGENT_E_ADB_PATH`
  - `MOBILE_AGENT_E_PERCEPTION_DEVICE`
  - `MOBILE_AGENT_E_STEP_SLEEP_SEC`
  - `MOBILE_AGENT_E_LIGHTWEIGHT_PERCEPTION`
- for a first smoke run, the only Mobile-Agent-E-specific env var you normally need is `MOBILE_AGENT_E_HOME`; the existing `PHONE_AGENT_*` values can be reused automatically.
- for the first real smoke run, set `MOBILE_AGENT_E_LIGHTWEIGHT_PERCEPTION=1`; in that mode the wrapper can bootstrap without `MOBILE_AGENT_E_CAPTION_API_KEY` and will use lightweight OCR/icon stubs instead of the full ModelScope perception stack.
- only set `MOBILE_AGENT_E_BASE_URL`, `MOBILE_AGENT_E_API_KEY`, or `MOBILE_AGENT_E_REASONING_MODEL` if you want Mobile-Agent-E to use a different endpoint or model from Open-AutoGLM.
- if `adb devices` works in your shell but the wrapped run still cannot see the target serial, point `MOBILE_AGENT_E_ADB_PATH` at the full SDK binary path, for example `/Users/<you>/Library/Android/sdk/platform-tools/adb`.
- Mobile-Agent-v3.5 now follows the same platform-side env mapping pattern:
- if `MOBILE_AGENT_V3_5_BASE_URL`, `MOBILE_AGENT_V3_5_API_KEY`, or `MOBILE_AGENT_V3_5_MODEL` are empty, the wrapper falls back to `PHONE_AGENT_BASE_URL`, `PHONE_AGENT_API_KEY`, and `PHONE_AGENT_MODEL`
- Mobile-Agent-v3.5-specific override envs are:
  - `MOBILE_AGENT_V3_5_HOME`
  - `MOBILE_AGENT_V3_5_BASE_URL`
  - `MOBILE_AGENT_V3_5_API_KEY`
  - `MOBILE_AGENT_V3_5_MODEL`
  - `MOBILE_AGENT_V3_5_ADB_PATH`
  - `MOBILE_AGENT_V3_5_APP_RESOLVER_API_KEY`
  - `MOBILE_AGENT_V3_5_APP_RESOLVER_BASE_URL`
  - `MOBILE_AGENT_V3_5_APP_RESOLVER_MODEL`
- for the first real smoke run, you normally only need `MOBILE_AGENT_V3_5_HOME`; the existing `PHONE_AGENT_*` endpoint values can be reused
- Mobile-Agent-v3.5 still depends on ADB Keyboard style text input support on device for reliable typing

See:

- `configs/runs/autoglm_mobilesafetybench.yml`
- `.env.example`

Mobile-Agent-v3.5 now also has:

- `configs/runs/mobile_agent_v3_5_mobilesafetybench.yml`

## Canonical Commands

### CLI help

```bash
snowl-mobile --help
python -m snowl_mobile.cli --help
```

### Registry discovery

```bash
snowl-mobile registry summary
snowl-mobile registry list-agents
snowl-mobile registry list-benchmarks
snowl-mobile registry list-bridges
```

### Device discovery

```bash
snowl-mobile devices list --config configs/runs/autoglm_mobilesafetybench.yml --device-mode existing_device
snowl-mobile devices health-check --config configs/runs/autoglm_mobilesafetybench.yml --device-mode existing_device
```

## AndroidWorld Benchmark-Side Validation

The repository now includes a checked-in AndroidWorld benchmark-side config:

```bash
snowl-mobile registry list-benchmarks --metadata
snowl-mobile validate-config configs/runs/androidworld_benchmark.yml
snowl-mobile plan configs/runs/androidworld_benchmark.yml
snowl-mobile benchmark-setup configs/runs/androidworld_benchmark.yml --output-dir /tmp/snowl-mobile-androidworld-setup
snowl-mobile benchmark-run configs/runs/androidworld_benchmark.yml --output-dir /tmp/snowl-mobile-androidworld-benchmark
```

Current scope:

- task discovery comes from the real AndroidWorld repository structure
- AndroidWorld-specific benchmark settings now live under `benchmarks[*].options`
- benchmark-native bootstrap, setup, observation capture, and native scoring now flow into the platform artifact layout
- the checked-in config defaults to `device_mode: fake` so the commands above are safe as repository-local smoke tests
- for real benchmark-side setup, a dedicated AndroidWorld Python 3.11 environment is recommended; this repository now works well with a repo-local path such as `.venvs/androidworld/bin/python`
- `benchmark-setup` now performs task-scoped app installation for the selected AndroidWorld task subset instead of forcing a full all-app installation pass
- for a real emulator, override the device binding explicitly:

```bash
snowl-mobile benchmark-setup configs/runs/androidworld_benchmark.yml --device-mode existing_device --adb-serial emulator-5554 --output-dir /tmp/snowl-mobile-androidworld-setup-real
snowl-mobile benchmark-run configs/runs/androidworld_benchmark.yml --device-mode existing_device --adb-serial emulator-5554 --output-dir /tmp/snowl-mobile-androidworld-benchmark-real
```

- AndroidWorld requires the emulator to be started from the command line with gRPC enabled, for example:

```bash
emulator -avd AndroidWorldAvd -no-snapshot -grpc 8554
```

- Upstream AndroidWorld also expects the AVD itself to be created as Android 13 / API 33 (`Tiramisu`). Merely naming the device `AndroidWorldAvd` is not enough. A quick verification is:

```bash
adb -s emulator-5554 shell getprop ro.build.version.sdk   # should print 33
adb -s emulator-5554 shell getprop ro.boot.qemu.avd_name  # should print AndroidWorldAvd
```

- `benchmark-run` does not execute an external agent yet, so `task_success` can remain `0` even when benchmark bootstrap succeeds

## First Real Run: Open-AutoGLM x AndroidWorld

Recommended first-run order:

1. Create or activate a dedicated Python environment for AndroidWorld and point `ANDROID_WORLD_PYTHON` at it.
   A repo-local Python 3.11 environment such as `.venvs/androidworld/bin/python` is recommended.
2. Launch the emulator from the command line with gRPC enabled.
   Make sure the AVD is actually Android 13 / API 33, not API 34/Android 14.
3. Confirm `adb devices` shows the target serial.
4. Validate and plan the checked-in real-pair config.
5. Run the first tiny real pair directly.
6. Use `benchmark-setup` only as an optional preflight if you want benchmark-side diagnostics or want to prepare a fresh emulator explicitly.
7. Summarize the run directory.

Example:

```bash
emulator -avd AndroidWorldAvd -no-snapshot -grpc 8554
adb devices

snowl-mobile validate-config configs/runs/autoglm_androidworld.yml
snowl-mobile plan configs/runs/autoglm_androidworld.yml

snowl-mobile run configs/runs/autoglm_androidworld.yml \
  --device-mode existing_device \
  --adb-serial emulator-5554 \
  --output-dir /tmp/snowl-mobile-open-autoglm-androidworld

snowl-mobile benchmark-setup configs/runs/androidworld_benchmark.yml \
  --device-mode existing_device \
  --adb-serial emulator-5554 \
  --output-dir /tmp/snowl-mobile-androidworld-setup-real

snowl-mobile summarize /tmp/snowl-mobile-open-autoglm-androidworld
```

Current scope:

- the canonical checked-in run config now defaults to the current full `android_world` suite, and smoke runs use `SNOWL_ANDROIDWORLD_SUITE_FAMILY=android` plus `SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend`
- the pair bridge owns AndroidWorld bootstrap, task setup, scoring, logs, and artifact capture
- the direct pair run now performs task-scoped app setup for the selected AndroidWorld task, so a fresh emulator does not strictly require a separate `benchmark-setup` pass first
- the first-pass step loop still executes actions through Open-AutoGLM's ADB device path rather than AndroidWorld-native JSONAction execution
- `benchmark-setup` is still useful as an optional benchmark-side preflight when you want richer AndroidWorld setup diagnostics before a real pair run
- recent bridge builds also classify model-endpoint failures separately from AndroidWorld bootstrap failures, and they reuse an already-installed accessibility forwarder on the emulator instead of forcing a fresh APK download every trial
- the bridge now also reuses already-installed task-scoped apps on the emulator when possible, and it sanitizes noisy `adb shell date` output before AndroidWorld datetime-sensitive tasks parse it

## Full Run: Open-AutoGLM x AndroidWorld

Use the same checked-in config for both smoke and full-suite runs.

Current checkout behavior:

- `configs/runs/autoglm_androidworld.yml` is the canonical config for both smoke and full-suite runs
- the default config uses `suite_family=android_world`, `tasks=[]`, `max_steps=30`, `timeout_sec=3600`, and `max_trial_retries=1`
- smoke runs use environment overrides: `SNOWL_ANDROIDWORLD_SUITE_FAMILY=android` and `SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend`
- the checked-in config keeps the same `artifact level = standard`, `device_mode = existing_device`, and `open_autoglm__androidworld` bridge; override concurrency at runtime with `--batch-size`
- in the current AndroidWorld checkout, the default full-suite plan expands to `148` trials

Recommended first full-run order:

1. Confirm the minimal config already works on the target emulator.
2. Keep using the dedicated `ANDROID_WORLD_PYTHON` environment.
3. Run `benchmark-setup` once on a fresh emulator before the first long run.
4. Validate and plan the same config in default full-suite mode.
5. Start the full run with a fresh platform `--output-dir`.
6. Watch `run.log` and rerun `summarize` while the run is in flight.

Commands:

```bash
snowl-mobile validate-config configs/runs/autoglm_androidworld.yml
snowl-mobile plan configs/runs/autoglm_androidworld.yml

snowl-mobile run configs/runs/autoglm_androidworld.yml \
  --device-mode existing_device \
  --adb-serial emulator-5554 \
  --output-dir /tmp/snowl-mobile-open-autoglm-androidworld-full

snowl-mobile summarize /tmp/snowl-mobile-open-autoglm-androidworld-full
```

Progress and result inspection:

- `tail -f /tmp/snowl-mobile-open-autoglm-androidworld-full/run.log`
- `snowl-mobile summarize /tmp/snowl-mobile-open-autoglm-androidworld-full`
- `/tmp/snowl-mobile-open-autoglm-androidworld-full/summary.json`
- `/tmp/snowl-mobile-open-autoglm-androidworld-full/events.jsonl`
- `/tmp/snowl-mobile-open-autoglm-androidworld-full/trials/<trial_id>/score.json`
- `/tmp/snowl-mobile-open-autoglm-androidworld-full/trials/<trial_id>/trajectory.json`
- `/tmp/snowl-mobile-open-autoglm-androidworld-full/trials/<trial_id>/raw/open_autoglm_androidworld/`

Checkpoint and restart notes:

- the full config leaves `SNOWL_ANDROIDWORLD_CHECKPOINT_DIR` and `SNOWL_ANDROIDWORLD_OUTPUT_PATH` blank by default
- if you set them, the bridge copies those upstream benchmark outputs back into each trial's `raw/open_autoglm_androidworld/` directory for inspection
- rerun the same full-run command with the same `--output-dir` to resume; completed/skipped trials are reused automatically, failed/aborted trials are scheduled again, and a partially written trial directory is cleared and rerun from the start

Current known limits:

- the first bridge still executes actions through Open-AutoGLM's ADB path rather than AndroidWorld-native JSONAction execution
- a real full-suite run has not been fully verified in this workspace yet because no local interpreter currently imports both AndroidWorld and Open-AutoGLM dependencies cleanly

## First Run: Mobile-Agent-E x AndroidWorld

Run the Open-AutoGLM AndroidWorld smoke path first on the same emulator if you want benchmark-side setup diagnostics already warmed up, then switch to the Mobile-Agent-E pair config.

Checked-in config:

- canonical run config: `configs/runs/mobile_agent_e_androidworld.yml`

Current checkout behavior:

- the checked-in config defaults to the current full `android_world` family, which is `148` planned trials in this checkout
- smoke runs use the same config with env overrides: `SNOWL_ANDROIDWORLD_SUITE_FAMILY=android` and `SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend`
- the checked-in config keeps the same `artifact level = standard`, `device_mode = existing_device`, and `mobile_agent_e__androidworld` bridge; override concurrency at runtime with `--batch-size`

Recommended first-run order:

1. Keep using the dedicated `ANDROID_WORLD_PYTHON` environment.
2. Reuse the same `AndroidWorldAvd` emulator launched with `-grpc 8554`.
3. Optionally run `benchmark-setup` once on a fresh emulator before the first long run.
4. Validate and plan the same checked-in config in smoke mode first.
5. Start the run with a fresh platform `--output-dir`.
6. Watch `run.log` and rerun `summarize` while the run is in flight.

Commands:

```bash
SNOWL_ANDROIDWORLD_SUITE_FAMILY=android \
SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend \
snowl-mobile validate-config configs/runs/mobile_agent_e_androidworld.yml

SNOWL_ANDROIDWORLD_SUITE_FAMILY=android \
SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend \
snowl-mobile plan configs/runs/mobile_agent_e_androidworld.yml

SNOWL_ANDROIDWORLD_SUITE_FAMILY=android \
SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend \
snowl-mobile run configs/runs/mobile_agent_e_androidworld.yml \
  --device-mode existing_device \
  --adb-serial emulator-5554 \
  --output-dir /tmp/snowl-mobile-mobile-agent-e-androidworld

snowl-mobile summarize /tmp/snowl-mobile-mobile-agent-e-androidworld
```

For the default full-suite run:

```bash
snowl-mobile validate-config configs/runs/mobile_agent_e_androidworld.yml
snowl-mobile plan configs/runs/mobile_agent_e_androidworld.yml

snowl-mobile run configs/runs/mobile_agent_e_androidworld.yml \
  --device-mode existing_device \
  --adb-serial emulator-5554 \
  --output-dir /tmp/snowl-mobile-mobile-agent-e-androidworld-full

snowl-mobile summarize /tmp/snowl-mobile-mobile-agent-e-androidworld-full
```

Progress and result inspection:

- `tail -f /tmp/snowl-mobile-mobile-agent-e-androidworld-full/run.log`
- `snowl-mobile summarize /tmp/snowl-mobile-mobile-agent-e-androidworld-full`
- `/tmp/snowl-mobile-mobile-agent-e-androidworld-full/summary.json`
- `/tmp/snowl-mobile-mobile-agent-e-androidworld-full/events.jsonl`
- `/tmp/snowl-mobile-mobile-agent-e-androidworld-full/trials/<trial_id>/score.json`
- `/tmp/snowl-mobile-mobile-agent-e-androidworld-full/trials/<trial_id>/trajectory.json`
- `/tmp/snowl-mobile-mobile-agent-e-androidworld-full/trials/<trial_id>/raw/mobile_agent_e_androidworld/`
- `/tmp/snowl-mobile-mobile-agent-e-androidworld-full/trials/<trial_id>/raw/mobile_agent_e/`

Current known limits:

- this bridge still keeps action execution inside Mobile-Agent-E's own ADB loop rather than rewriting actions into AndroidWorld-native `JSONAction`
- a real full-suite run has not been fully verified in this workspace yet because no local interpreter currently imports both AndroidWorld and Mobile-Agent-E dependencies cleanly
- the minimal AndroidWorld smoke path now honors `MOBILE_AGENT_E_LIGHTWEIGHT_PERCEPTION=1`, so the first bridge no longer eagerly requires `torch` just to start the wrapped runner

## First Run: Mobile-Agent-v3.5 x AndroidWorld

This path now reuses the same AndroidWorld benchmark adapter, benchmark-native bootstrap/scoring, and output-dir resume behavior as the Open-AutoGLM and Mobile-Agent-E AndroidWorld pairs. Mobile-Agent-v3.5 still owns its own wrapped runner and ADB action loop.

Checked-in config:

- canonical run config: `configs/runs/mobile_agent_v3_5_androidworld.yml`

Current checkout behavior:

- the checked-in config defaults to the current full `android_world` family, which is `148` planned trials in this checkout
- smoke runs use the same config with env overrides: `SNOWL_ANDROIDWORLD_SUITE_FAMILY=android` and `SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend`
- the checked-in config keeps the same `artifact level = standard`, `device_mode = existing_device`, and `mobile_agent_v3_5__androidworld` bridge; override concurrency at runtime with `--batch-size`

Recommended first-run order:

1. Keep using the dedicated `ANDROID_WORLD_PYTHON` environment.
2. Reuse the same `AndroidWorldAvd` emulator launched with `-grpc 8554`.
3. Optionally run `benchmark-setup` once on a fresh emulator before the first long run.
4. Validate and plan the same checked-in config in smoke mode first.
5. Start the run with a fresh platform `--output-dir`.
6. Watch `run.log` and rerun `summarize` while the run is in flight.

Commands:

```bash
SNOWL_ANDROIDWORLD_SUITE_FAMILY=android \
SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend \
snowl-mobile validate-config configs/runs/mobile_agent_v3_5_androidworld.yml

SNOWL_ANDROIDWORLD_SUITE_FAMILY=android \
SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend \
snowl-mobile plan configs/runs/mobile_agent_v3_5_androidworld.yml

SNOWL_ANDROIDWORLD_SUITE_FAMILY=android \
SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend \
snowl-mobile run configs/runs/mobile_agent_v3_5_androidworld.yml \
  --device-mode existing_device \
  --adb-serial emulator-5554 \
  --output-dir /tmp/snowl-mobile-mobile-agent-v3-5-androidworld

snowl-mobile summarize /tmp/snowl-mobile-mobile-agent-v3-5-androidworld
```

For the default full-suite run:

```bash
snowl-mobile validate-config configs/runs/mobile_agent_v3_5_androidworld.yml
snowl-mobile plan configs/runs/mobile_agent_v3_5_androidworld.yml

snowl-mobile run configs/runs/mobile_agent_v3_5_androidworld.yml \
  --device-mode existing_device \
  --adb-serial emulator-5554 \
  --output-dir /tmp/snowl-mobile-mobile-agent-v3-5-androidworld-full

snowl-mobile summarize /tmp/snowl-mobile-mobile-agent-v3-5-androidworld-full
```

Progress and result inspection:

- `tail -f /tmp/snowl-mobile-mobile-agent-v3-5-androidworld-full/run.log`
- `snowl-mobile summarize /tmp/snowl-mobile-mobile-agent-v3-5-androidworld-full`
- `/tmp/snowl-mobile-mobile-agent-v3-5-androidworld-full/summary.json`
- `/tmp/snowl-mobile-mobile-agent-v3-5-androidworld-full/events.jsonl`
- `/tmp/snowl-mobile-mobile-agent-v3-5-androidworld-full/trials/<trial_id>/score.json`
- `/tmp/snowl-mobile-mobile-agent-v3-5-androidworld-full/trials/<trial_id>/trajectory.json`
- `/tmp/snowl-mobile-mobile-agent-v3-5-androidworld-full/trials/<trial_id>/raw/mobile_agent_v3_5_androidworld/`
- `/tmp/snowl-mobile-mobile-agent-v3-5-androidworld-full/trials/<trial_id>/raw/mobile_agent_v3_5/`

Current known limits:

- this bridge still keeps action execution inside Mobile-Agent-v3.5's own ADB loop rather than rewriting actions into AndroidWorld-native `JSONAction`
- a real full-suite run has not been fully verified in this workspace yet because no local interpreter currently imports both AndroidWorld and Mobile-Agent-v3.5 dependencies cleanly

## First Real Run: Open-AutoGLM x MobileSafetyBench

### 1. Start an Android emulator manually

The current recommended path is `existing_device`, which means the emulator must already be running before `snowl-mobile run`.

Examples:

- Start it from Android Studio
- or run `emulator -avd <your_avd_name>`

Confirm ADB connectivity:

```bash
adb devices
```

You should see at least one entry like `emulator-5554`.

### 2. Check that the platform sees the real adapters

```bash
snowl-mobile registry list-agents
snowl-mobile registry list-benchmarks
```

Expected names include:

- `mobile_agent_e`
- `mobile_agent_v3_5`
- `open_autoglm`
- `androidworld`
- `mobilesafetybench`
- `mobile_agent_e__androidworld`
- `mobile_agent_v3_5__androidworld`
- `open_autoglm__androidworld`

### 3. Validate the minimal real-pair config

```bash
snowl-mobile validate-config configs/runs/autoglm_mobilesafetybench.yml
```

### 4. Expand the run plan

```bash
snowl-mobile plan configs/runs/autoglm_mobilesafetybench.yml
```

This should show:

- `bridge_id = open_autoglm__mobilesafetybench`
- `pair_recipe_id = open_autoglm_mobilesafetybench_existing_device`

### 5. Verify devices

```bash
snowl-mobile devices list --config configs/runs/autoglm_mobilesafetybench.yml --device-mode existing_device
snowl-mobile devices health-check --config configs/runs/autoglm_mobilesafetybench.yml --device-mode existing_device
```

If you want to pin a specific emulator:

```bash
snowl-mobile devices list --config configs/runs/autoglm_mobilesafetybench.yml --device-mode existing_device --adb-serial emulator-5554
```

### 6. Run the first real pair

```bash
snowl-mobile run configs/runs/autoglm_mobilesafetybench.yml \
  --model-name Qwen2.5-VL-72B-Instruct \
  --base-url https://your-openai-compatible-endpoint/v1 \
  --api-key <your-api-key> \
  --max-steps 20 \
  --device-mode existing_device \
  --adb-serial emulator-5554 \
  --output-dir ./tmp/snowl-mobile-real-pair
```

`--output-dir` is now the actual run directory. The CLI writes `run.log`, `summary.json`, and `trials/` directly under that path instead of creating an extra timestamp subdirectory. If you rerun the same command with the same `--output-dir`, the platform resumes automatically, reuses completed/skipped trials, and reruns failed or partial ones.

You do not need to create this config by hand for each model. The repository now ships a generic checked-in pair config, and the default workflow is:

- keep using `configs/runs/autoglm_mobilesafetybench.yml`
- pass `--model-name`, or export `PHONE_AGENT_MODEL` in your shell
- keep `provider = openai_compatible` and `api_style = openai_chat` unless the pair contract changes

If you want the platform to schedule onto two existing emulators in parallel and immediately refill whichever one becomes idle first, run:

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
  --output-dir ./tmp/snowl-mobile-autoglm-mobilesafetybench-batch2
```

This checked-in config now defaults to all benchmark tasks:

- `task_source.selector = ${SNOWL_TASK_SELECTOR:-all}`

If you want a smaller smoke run instead of the full task set:

- set `SNOWL_TASK_SELECTOR='task_category=text_message_sending,task_id=high_risk_001,limit=1'`
- or edit `benchmarks[*].task_source.selector` directly
- `limit=-1` also means “no limit”

Each selected task becomes its own trial. Before each trial, the platform runs the configured reset flow again (`restore_snapshot_then_seed` here), so later tasks do not inherit the previous task state.

### 7. Summarize the run

```bash
snowl-mobile summarize ./tmp/snowl-mobile-real-pair
```

## Experimental Real Pair Run: Mobile-Agent-E x MobileSafetyBench

This path still uses the Mobile-Agent-E subprocess wrapper, but it now runs through the dedicated `mobile_agent_e__mobilesafetybench` pair bridge.

What now happens before the first model call:

- the leased emulator is restored to the configured snapshot
- MobileSafetyBench runs task seeding and environment initialization
- the bridge captures a real bootstrap observation from `MobileSafetyEnv`
- pair-level raw artifacts are written under `raw/mobile_agent_e_mobilesafetybench/`
- only then does the Mobile-Agent-E subprocess start

Before running it for real, make sure:

- `references/agents/MobileAgent/Mobile-Agent-E/` exists
- the Mobile-Agent-E requirements are installed into the current Python environment, or `MOBILE_AGENT_E_LIGHTWEIGHT_PERCEPTION=1` is enabled for the first smoke run
- `PHONE_AGENT_BASE_URL`, `PHONE_AGENT_API_KEY`, and `PHONE_AGENT_MODEL` are exported in your shell, passed on the CLI via `--base-url`, `--api-key`, and `--model-name`, or encoded in the run config itself
- `MOBILE_AGENT_E_CAPTION_API_KEY` is set if you disable lightweight perception and keep caption mode on `api`
- an Android emulator is already running and visible in `adb devices`
- ADB keyboard style text input support is installed on device if the task needs typing
- if needed, `MOBILE_AGENT_E_ADB_PATH` points to the exact SDK `adb` binary that can see your emulator
- after snapshot restore, the wrapped path now waits briefly for the emulator to become adb-ready again; if the first probe still fails, wait a few seconds and rerun with a fresh `--output-dir`
- after environment initialization, the pair bridge now emits live progress messages while the upstream subprocess is planning or waiting on model responses, so the terminal is no longer silent for several minutes
- completed steps now materialize incrementally into `trial.log`, `steps/*.jpg|xml`, and `raw/mobile_agent_e_mobilesafetybench/steps/*.console.txt` instead of appearing only after the subprocess exits

Canonical config:

- `configs/runs/mobile_agent_e_mobilesafetybench.yml`

Why this is now a single file:

- the previous `minimal` and `full` files only differed in default selector and a few runtime knobs
- the structure, adapters, backend, artifacts, and CLI flow were identical
- the unified file now defaults to the full 250-task manifest, while smoke runs use env overrides like `SNOWL_TASK_SELECTOR`

Recommended first-run order:

1. Start the emulator manually.
2. Run `adb devices` and confirm the target serial appears as `device`.
3. Run `snowl-mobile validate-config configs/runs/mobile_agent_e_mobilesafetybench.yml`.
4. Run `snowl-mobile plan configs/runs/mobile_agent_e_mobilesafetybench.yml`.
   This should now show `bridge_id = mobile_agent_e__mobilesafetybench` and `pair_recipe_id = mobile_agent_e_mobilesafetybench_existing_device`.
5. Export or encode the runtime settings directly: ensure `MOBILE_AGENT_E_HOME` is resolvable, set `MOBILE_AGENT_E_LIGHTWEIGHT_PERCEPTION=1`, and pass `--base-url`, `--api-key`, or `--model-name` only if you want a different endpoint from the checked-in config defaults.
6. Export `SNOWL_TASK_SELECTOR='task_category=text_message_sending,task_id=low_risk_001,limit=1'` for the first smoke run.
7. Run the real one-task smoke command.
8. Run `snowl-mobile summarize <run_dir>`.

Commands:

```bash
export SNOWL_TASK_SELECTOR='task_category=text_message_sending,task_id=low_risk_001,limit=1'
snowl-mobile validate-config configs/runs/mobile_agent_e_mobilesafetybench.yml
snowl-mobile plan configs/runs/mobile_agent_e_mobilesafetybench.yml
snowl-mobile run configs/runs/mobile_agent_e_mobilesafetybench.yml \
  --device-mode existing_device \
  --adb-serial emulator-5554 \
  --output-dir ./tmp/snowl-mobile-mobile-agent-e
snowl-mobile summarize ./tmp/snowl-mobile-mobile-agent-e
```

After the smoke path is stable on your emulator and model endpoint, switch back to the full-manifest default:

```bash
unset SNOWL_TASK_SELECTOR
snowl-mobile validate-config configs/runs/mobile_agent_e_mobilesafetybench.yml
snowl-mobile plan configs/runs/mobile_agent_e_mobilesafetybench.yml
snowl-mobile run configs/runs/mobile_agent_e_mobilesafetybench.yml \
  --device-mode existing_device \
  --adb-serial emulator-5554 \
  --output-dir ./tmp/snowl-mobile-mobile-agent-e-full
snowl-mobile summarize ./tmp/snowl-mobile-mobile-agent-e-full
```

To watch progress during a long run:

- `tail -f ./tmp/snowl-mobile-mobile-agent-e-full/run.log`
- `tail -f ./tmp/snowl-mobile-mobile-agent-e-full/trials/<trial_id>/trial.log`
- inspect `./tmp/snowl-mobile-mobile-agent-e-full/events.jsonl`
- inspect `./tmp/snowl-mobile-mobile-agent-e-full/trials/<trial_id>/raw/mobile_agent_e_mobilesafetybench/`
- inspect `./tmp/snowl-mobile-mobile-agent-e-full/trials/<trial_id>/raw/mobile_agent_e/`
- rerun the same `snowl-mobile run ... --output-dir ./tmp/snowl-mobile-mobile-agent-e-full` command to resume after an interruption

Current limitations of this path:

- MobileSafetyBench reset/seed and final-state evaluation now run inside a dedicated pair bridge
- the upstream repo still expects a heavy local dependency stack and may prefer Python 3.10 in practice
- benchmark context is now forwarded into the wrapped task instruction and raw artifacts, but MobileSafetyBench evaluator progress is still not updated step-by-step the way the Open-AutoGLM pair bridge does it because Mobile-Agent-E still executes its own ADB loop outside `MobileSafetyEnv.step()`
- start with a one-task `SNOWL_TASK_SELECTOR` smoke run before the full-manifest default; if the smoke run is not stable yet, the full run will mostly multiply that instability across the task set
- `batch_size > 1` is still not recommended for this path
- current long-run behavior still depends on the host Python environment, local adb/Appium stability, and model endpoint uptime; the platform can resume and classify failures, but it does not hide these limits
- on macOS, `/tmp/...` is backed by `/private/tmp/...`; if you pass `--output-dir /tmp/...`, check `/private/tmp/...` if Finder or terminal listing looks inconsistent
- when `MOBILE_AGENT_E_LIGHTWEIGHT_PERCEPTION` is disabled, the first full-perception run may spend a long time downloading or loading ModelScope OCR / GroundingDINO assets before any step artifacts appear; watch `raw/mobile_agent_e/runner.stdout.txt` live
- if the wrapped run now fails with `MODEL_CALL_FAILED`, inspect `raw/mobile_agent_e/reasoning_request_diagnostics.json`; the runner records HTTP status / body previews and request exceptions there before surfacing the generic failure
- if you want the live progress messages to be more visible in the console, run `snowl-mobile -v run ...` and keep a second shell on the current trial's `trial.log`

## Experimental Real Pair Run: Mobile-Agent-v3.5 x MobileSafetyBench

This path now uses the dedicated `mobile_agent_v3_5__mobilesafetybench` pair bridge. The platform owns config loading, device leasing, MobileSafetyBench reset/seed/bootstrap, bridge-level observations, trajectory export, and final-state evaluation, while the Mobile-Agent-v3.5 subprocess wrapper still owns screenshot capture, prompt construction, model calls, and ADB actions.

The current wrapper path is intentionally faithful to upstream behavior: it does not rewrite Mobile-Agent-v3.5 action choices into benchmark-aware fallback actions. The platform only performs execution translation that is required to run the upstream agent in the current environment, plus streaming logs and artifact capture.

Before running it for real, make sure:

- `references/agents/MobileAgent/Mobile-Agent-v3.5/` exists
- `openai`, `pillow`, and `numpy` are installed in the current Python environment
- `MOBILE_AGENT_V3_5_HOME` is set, and either `MOBILE_AGENT_V3_5_*` or fallback `PHONE_AGENT_*` endpoint vars are available
- an Android emulator is already running and visible in `adb devices`
- if needed, `MOBILE_AGENT_V3_5_ADB_PATH` points to the exact SDK `adb` binary that can see your emulator
- the device supports ADB keyboard style text input if the task needs typing

Run config:

- `configs/runs/mobile_agent_v3_5_mobilesafetybench.yml`

First smoke vs full:

- the checked-in config defaults to `selector=all`, which is `250` MobileSafetyBench tasks in this checkout
- the same file can be turned into a one-task smoke run by exporting `SNOWL_TASK_SELECTOR='task_category=text_message_sending,task_id=low_risk_001,limit=1'`
- the checked-in config keeps `timeout_sec=2400`, `artifact level = standard`, `device_mode = existing_device`, `max_trial_retries = 1`, and the same pair bridge for both smoke and full runs; override concurrency with `--batch-size`

Recommended first-run order:

1. Start the emulator manually.
2. Run `adb devices` and confirm the target serial appears as `device`.
3. Export a one-task `SNOWL_TASK_SELECTOR` first.
4. Only after the smoke path is stable, unset it and switch back to the full-manifest default.
5. Use `snowl-mobile summarize <run_dir>` after each run.

Minimal smoke commands:

```bash
export SNOWL_TASK_SELECTOR='task_category=text_message_sending,task_id=low_risk_001,limit=1'
snowl-mobile validate-config configs/runs/mobile_agent_v3_5_mobilesafetybench.yml
snowl-mobile plan configs/runs/mobile_agent_v3_5_mobilesafetybench.yml
snowl-mobile run configs/runs/mobile_agent_v3_5_mobilesafetybench.yml \
  --device-mode existing_device \
  --adb-serial emulator-5554 \
  --output-dir ./tmp/snowl-mobile-mobile-agent-v3-5-smoke
snowl-mobile summarize ./tmp/snowl-mobile-mobile-agent-v3-5-smoke
unset SNOWL_TASK_SELECTOR
```

Canonical full-run commands:

```bash
snowl-mobile validate-config configs/runs/mobile_agent_v3_5_mobilesafetybench.yml
snowl-mobile plan configs/runs/mobile_agent_v3_5_mobilesafetybench.yml
snowl-mobile run configs/runs/mobile_agent_v3_5_mobilesafetybench.yml \
  --device-mode existing_device \
  --adb-serial emulator-5554 \
  --output-dir ./tmp/snowl-mobile-mobile-agent-v3-5-full
snowl-mobile summarize ./tmp/snowl-mobile-mobile-agent-v3-5-full
```

To validate the same pair path without touching a real device:

```bash
export SNOWL_TASK_SELECTOR='task_category=text_message_sending,task_id=low_risk_001,limit=1'
snowl-mobile run configs/runs/mobile_agent_v3_5_mobilesafetybench.yml \
  --device-mode fake \
  --output-dir ./tmp/snowl-mobile-mobile-agent-v3-5-fake
unset SNOWL_TASK_SELECTOR
```

Look under:

- `./tmp/snowl-mobile-mobile-agent-v3-5-full/run.log`
- `./tmp/snowl-mobile-mobile-agent-v3-5-full/summary.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/trial.log`
- `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/score.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/trajectory.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5_mobilesafetybench/bridge_request.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5_mobilesafetybench/environment_init.console.txt`
- `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5_mobilesafetybench/bootstrap_observation.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5_mobilesafetybench/final_observation.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5_mobilesafetybench/final_result.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5/request.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5/task_payload.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5/benchmark_context.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5/runner_request.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5/runner_result.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5/wrapped_result.json`
- `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5/steps/0001.model_response.json`

To watch progress during a long run:

- `tail -f ./tmp/snowl-mobile-mobile-agent-v3-5-full/run.log`
- `tail -f ./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/trial.log`
- inspect `./tmp/snowl-mobile-mobile-agent-v3-5-full/events.jsonl`
- inspect `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5_mobilesafetybench/`
- inspect `./tmp/snowl-mobile-mobile-agent-v3-5-full/trials/<trial_id>/raw/mobile_agent_v3_5/`
- rerun the same `snowl-mobile run ... --output-dir ./tmp/snowl-mobile-mobile-agent-v3-5-full` command to resume after an interruption

Current limitations of this path:

- step-by-step evaluator progress is still partial because Mobile-Agent-v3.5 acts through its own ADB loop outside `MobileSafetyEnv.step()`
- benchmark-aware app aliasing is bridge-owned but still intentionally minimal in this phase
- the wrapped path still depends on the host Python environment and on upstream `mobile_use` dependencies
- start with a one-task `SNOWL_TASK_SELECTOR` override before the full-manifest default; if the smoke run is not stable yet, the full run will mostly multiply that instability across the task set
- `batch_size > 1` is still not recommended for this path
- current long-run behavior still depends on host Python, adb/Appium stability, and model endpoint uptime; the platform can resume and classify failures, but it does not hide these limits
- on some emulators, outer snapshot restore or adb health probes may stall before the pair bridge begins; if that happens, restart the emulator, confirm `adb devices`, and retry a one-task `SNOWL_TASK_SELECTOR` smoke run first

## Where To Configure Key Fields

- Agent name:
  - `agents[*].id`
- Benchmark name:
  - `benchmarks[*].id`
- Model provider / model id / modalities:
  - `models[*]`
- Device mode:
  - `devices.device_mode`
  - can be overridden by `--device-mode`
- ADB serial:
  - `devices.adb_serials`
  - or via `--adb-serial`
- Batch size:
  - `runtime.batch_size`
- Task selection / task limit:
  - `benchmarks[*].task_source.selector`
  - default is `all`; use `limit=N` for sampling or `limit=-1` for explicit full-run semantics
- Artifact level:
  - `artifacts.level`

## Where To Watch Progress And Results

During the run:

- progress and diagnostics are printed to the terminal
- the run directory is:
  - your explicit `--output-dir`
  - or `runs/<run_name_slug>/` if you omit `--output-dir`
- run-level logs go to `<run_dir>/run.log`
  - this file is intentionally high-level: task index, instruction, trial path, reset status, execution start, evaluation start/completion, and final outcome
- per-trial logs go to `<run_dir>/trials/<trial_id>/trial.log`
  - this file records task-scoped execution details for a single task
  - on the Mobile-Agent-E pair path it now also includes reconstructed step summaries such as manager thought, current subgoal, action thought, action description, selected action, and reflection outcome

After the run:

- summary:
  - `<run_dir>/summary.json`
- plan:
  - `<run_dir>/plan.json`
- run events:
  - `<run_dir>/events.jsonl`
- per-trial metadata:
  - `<run_dir>/trials/<trial_id>/meta.json`
  - internal lifecycle and failure history for reproducibility and debugging
- per-trial runtime recipe:
  - `<run_dir>/trials/<trial_id>/runtime_recipe.json`
  - the exact bridge / backend / reset / worker settings used by this trial
- per-trial score:
  - `<run_dir>/trials/<trial_id>/score.json`
  - the platform-facing MobileSafetyBench evaluation result for that task
- per-trial trajectory:
  - `<run_dir>/trials/<trial_id>/trajectory.json`
  - a user-facing task trace that keeps only the task instruction, Thought, Action, Action Input, summarized Observation, and screenshot/XML paths
- raw model responses:
  - `<run_dir>/trials/<trial_id>/raw/open_autoglm_mobilesafetybench/steps/0001.model_response.txt`
  - `<run_dir>/trials/<trial_id>/raw/open_autoglm_mobilesafetybench/steps/0001.model_response.json`
  - the same paths are also surfaced inside `trajectory.json`
- Mobile-Agent-E wrapped-agent raw outputs:
  - `<run_dir>/trials/<trial_id>/raw/mobile_agent_e/request.json`
  - `<run_dir>/trials/<trial_id>/raw/mobile_agent_e/runner_request.json`
  - `<run_dir>/trials/<trial_id>/raw/mobile_agent_e/runner_result.json`
  - `<run_dir>/trials/<trial_id>/raw/mobile_agent_e/wrapped_result.json`
  - `<run_dir>/trials/<trial_id>/raw/mobile_agent_e/steps/0001.model_response.json`
- Mobile-Agent-E pair-bridge step transcript outputs:
  - `<run_dir>/trials/<trial_id>/raw/mobile_agent_e_mobilesafetybench/steps/0001.console.txt`
  - `<run_dir>/trials/<trial_id>/raw/mobile_agent_e_mobilesafetybench/steps/0001.model_response.txt`
  - `<run_dir>/trials/<trial_id>/raw/mobile_agent_e_mobilesafetybench/steps/0001.model_response.json`
- step screenshots and XML:
  - `<run_dir>/trials/<trial_id>/steps/0001.png`
  - `<run_dir>/trials/<trial_id>/steps/0001.xml`
  - on the Mobile-Agent-E pair path, these step artifacts now prefer the post-action observation that follows each action, so the last successful step also keeps its final screenshot/XML sidecar when the upstream runner emits them

## Manual And Codex-Assisted Integration Workflows

Agent integration:

- `docs/integrate-agent.md`
- `docs/prompts/integrate-agent-prompt.md`

Benchmark integration:

- `docs/integrate-benchmark.md`
- `docs/prompts/integrate-benchmark-prompt.md`

Pair-specific bridge integration:

- `docs/integrate-pair.md`

Readiness and operational docs:

- `docs/integration-readiness-checklist.md`
- `docs/quickstart.md`
- `docs/troubleshooting.md`

## Repository Layout

```text
src/snowl_mobile/   Core package
configs/            Real and integration config examples
docs/               User-facing and integration docs
examples/           Generated scaffolds and future-facing examples
references/         User-managed third-party repos
tests/              Unit, integration, and e2e tests
runs/               Default artifact output root
scripts/            Developer helpers
```

## Useful Example Commands

```bash
make lint
make test
make validate-example
make plan-example
make dry-run-example
make devices-list-example
make devices-health-check-example
make run-example
```

## More Pair-Specific Notes

See:

- `docs/integrations/mobile-agent-e.md`
- `docs/integrations/mobile-agent-v3-5.md`
- `docs/integrations/open-autoglm.md`
- `docs/integrations/mobilesafetybench.md`
- `docs/integrations/open-autoglm-mobilesafetybench.md`

## Troubleshooting

Start with:

- `docs/troubleshooting.md`

Common first-run failure causes:

- `mobile_agent_e`, `open_autoglm`, or `mobilesafetybench` not found in registry
- `mobile_agent_v3_5` not found in registry, or `MOBILE_AGENT_V3_5_HOME` points to the wrong local checkout
- wrong local clone path under `references/`
- missing upstream Python dependencies in the active environment
- missing `PHONE_AGENT_BASE_URL` / `PHONE_AGENT_API_KEY` / `APPIUM_BIN`
- missing `MOBILE_AGENT_E_HOME`, or missing both `PHONE_AGENT_*` and `MOBILE_AGENT_E_*` reasoning endpoint vars
- emulator not visible through `adb devices`
- case-sensitive path mismatch for `references/benchmarks/mobilesafetybench`

## License

This repository is released under the MIT License. 
