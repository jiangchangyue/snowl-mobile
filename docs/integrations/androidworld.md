# AndroidWorld Integration

This document records the current AndroidWorld benchmark integration status in `snowl-mobile`.

Repository path:

- `references/benchmarks/android_world/`

The adapter is registered as:

- `androidworld`

## Current Status

- The benchmark adapter is now registered in the builtin registry.
- `validate-config`, `plan`, `benchmark-setup`, and `benchmark-run` now work with checked-in configs.
- `open_autoglm__androidworld` is now registered as the first minimal real pair bridge for AndroidWorld.
- `mobile_agent_e__androidworld` is now registered as a second AndroidWorld pair bridge.
- `mobile_agent_v3_5__androidworld` is now registered as a third AndroidWorld pair bridge.
- Task discovery is backed by the real upstream repository structure:
  - `android_world/registry.py`
  - `android_world/task_metadata.json`
  - `android_world/task_evals/miniwob/miniwob_registry.py`
  - `android_world/task_evals/information_retrieval/proto/tasks.textproto`
- Benchmark-native setup, bootstrap observation capture, and native scoring now land in the platform artifact layout.
- A first minimal real `open_autoglm x androidworld` closure is now wired through `validate-config -> plan -> run -> summarize`.

## Current Adapter Shape

The current adapter now covers the benchmark-facing runtime foundation:

- benchmark contract declaration
- repository path resolution
- suite-family aware task discovery
- minimal benchmark-native option mapping through `benchmarks[*].options`
- deterministic expansion for `n_task_combinations`
- registry metadata for device/runtime expectations
- benchmark-side probe request building
- benchmark-side subprocess helper support for dedicated Python environments
- benchmark-native raw artifact capture under `raw/androidworld/`

Current checked-in options:

- `suite_family`
- `tasks`
- `n_task_combinations`
- `task_random_seed`
- `fixed_task_seed`
- `perform_emulator_setup`
- `checkpoint_dir`
- `output_path`
- `adb_path`
- `console_port`
- `grpc_port`
- `freeze_datetime`

## Repository Analysis

Task discovery:

- `android_world/registry.py::TaskRegistry`
- `android_world/suite_utils.py::create_suite`
- Android tasks are class-registered; MiniWoB and information-retrieval tasks are generated dynamically from separate sources

Environment init / reset:

- `android_world/env/env_launcher.py::load_and_setup_env`
- `android_world/env/interface.py::AsyncEnv.reset`
- `android_world/task_evals/task_eval.py::TaskEval.initialize_task`

Scoring / result capture:

- `android_world/task_evals/task_eval.py::TaskEval.is_successful`
- `android_world/suite_utils.py::process_episodes`
- `android_world/checkpointer.py::IncrementalCheckpointer`

Recommended integration mode:

- `hybrid`

Reason:

- AndroidWorld exposes clean task/env/scoring Python surfaces.
- Its native run loop still owns env bootstrap, agent wiring, and checkpoint persistence in a benchmark-specific shape.
- A hybrid adapter keeps task/scoring semantics close to upstream while leaving room for a platform-owned pair bridge later.

## Minimal Validation Path

Config:

- `configs/integrations/androidworld/minimal.yml`
- `configs/runs/androidworld_benchmark.yml`
- `configs/runs/autoglm_androidworld.yml`
- `configs/runs/mobile_agent_e_androidworld.yml`
- `configs/runs/mobile_agent_v3_5_androidworld.yml`

Suggested commands:

```bash
PYTHONPATH=src python3 -m snowl_mobile registry list-benchmarks --metadata
PYTHONPATH=src python3 -m snowl_mobile validate-config configs/runs/androidworld_benchmark.yml
PYTHONPATH=src python3 -m snowl_mobile plan configs/runs/androidworld_benchmark.yml
PYTHONPATH=src python3 -m snowl_mobile benchmark-setup configs/runs/androidworld_benchmark.yml --output-dir /tmp/snowl-mobile-androidworld-setup
PYTHONPATH=src python3 -m snowl_mobile benchmark-run configs/runs/androidworld_benchmark.yml --output-dir /tmp/snowl-mobile-androidworld-benchmark
```

For a real emulator:

```bash
PYTHONPATH=src python3 -m snowl_mobile benchmark-setup configs/runs/androidworld_benchmark.yml --device-mode existing_device --adb-serial emulator-5554 --output-dir /tmp/snowl-mobile-androidworld-setup-real
PYTHONPATH=src python3 -m snowl_mobile benchmark-run configs/runs/androidworld_benchmark.yml --device-mode existing_device --adb-serial emulator-5554 --output-dir /tmp/snowl-mobile-androidworld-benchmark-real
```

AndroidWorld expects the emulator to be launched with gRPC enabled, for example:

```bash
emulator -avd AndroidWorldAvd -no-snapshot -grpc 8554
```

The upstream README also expects the AVD itself to be Android 13 / API 33 (`Tiramisu`). Naming the AVD `AndroidWorldAvd` is not enough. A quick check is:

```bash
adb -s emulator-5554 shell getprop ro.build.version.sdk
```

It should print `33`.

## Current Limitations

- `benchmark-run` does not execute an external agent yet, so `task_success` can remain `0` even when benchmark bootstrap succeeds.
- The first `open_autoglm x androidworld` bridge is intentionally minimal: AndroidWorld owns bootstrap and scoring, while Open-AutoGLM still executes actions through its ADB device path.
- The direct `open_autoglm x androidworld` run now performs task-scoped AndroidWorld app setup inside the pair bridge, so a fresh emulator can often be used without a separate `benchmark-setup` command first.
- A dedicated AndroidWorld worker env is still recommended. The platform can point the bridge subprocess at `ANDROID_WORLD_PYTHON` or `benchmarks[*].options.python_executable`, but it does not create that env for you yet.
- The checked-in real-pair config intentionally stays tiny: one device, `batch_size=1`, and a small Android task subset.
- The checked-in full-suite config is now available, but a real full-suite verification is still pending on a machine that has one interpreter capable of importing both AndroidWorld and Open-AutoGLM dependencies.
- AndroidWorld full runs now inherit the platform's standard same-directory resume behavior: rerunning the same command with the same `--output-dir` skips trials that already have terminal `meta.json + score.json` artifacts. This is trial-level artifact resume, not mid-trial step checkpoint resume.
- The benchmark still recommends a dedicated Python environment for real execution; the platform now lets you point `python_executable` or `ANDROID_WORLD_PYTHON` at that env, but it does not create the environment for you yet.
- `mobile_agent_e x androidworld` is now available through a first minimal pair bridge, but a real full-suite verification is still pending on a machine that has one interpreter capable of importing both AndroidWorld and Mobile-Agent-E dependencies.
- `mobile_agent_v3_5 x androidworld` is now available through a first minimal pair bridge, but a real long-run/full-suite verification is still pending on a machine that has one interpreter capable of importing both AndroidWorld and Mobile-Agent-v3.5 dependencies.

## First Real Pair

Suggested first-run sequence:

```bash
SNOWL_ANDROIDWORLD_SUITE_FAMILY=android \
SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend \
PYTHONPATH=src python3 -m snowl_mobile validate-config configs/runs/autoglm_androidworld.yml
SNOWL_ANDROIDWORLD_SUITE_FAMILY=android \
SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend \
PYTHONPATH=src python3 -m snowl_mobile plan configs/runs/autoglm_androidworld.yml
SNOWL_ANDROIDWORLD_SUITE_FAMILY=android \
SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend \
PYTHONPATH=src python3 -m snowl_mobile run configs/runs/autoglm_androidworld.yml --device-mode existing_device --adb-serial emulator-5554 --output-dir /tmp/snowl-mobile-open-autoglm-androidworld
PYTHONPATH=src python3 -m snowl_mobile benchmark-setup configs/runs/androidworld_benchmark.yml --device-mode existing_device --adb-serial emulator-5554 --output-dir /tmp/snowl-mobile-androidworld-setup-real
PYTHONPATH=src python3 -m snowl_mobile summarize /tmp/snowl-mobile-open-autoglm-androidworld
```

Key artifact paths:

- `trials/<trial_id>/score.json`
- `trials/<trial_id>/trajectory.json`
- `trials/<trial_id>/raw/open_autoglm_androidworld/bridge_request.json`
- `trials/<trial_id>/raw/open_autoglm_androidworld/final_result.json`
- `trials/<trial_id>/raw/open_autoglm_androidworld/steps/0001.model_response.json`

## Full-Suite Config

The repository now keeps a single canonical Open-AutoGLM config:

- `configs/runs/autoglm_androidworld.yml`

Current checkout behavior:

- default full-suite: `suite_family=android_world`
- default full-suite: `tasks=[]`, which means "discover the whole family from the upstream registry"
- `n_task_combinations=1`
- `batch_size=1`
- `max_steps=30`
- `timeout_sec=3600`
- `max_trial_retries=1`
- smoke runs override the same config with `SNOWL_ANDROIDWORLD_SUITE_FAMILY=android` and `SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend`
- the default full-suite plan is `148` trials in this checkout

Suggested commands:

```bash
PYTHONPATH=src python3 -m snowl_mobile validate-config configs/runs/autoglm_androidworld.yml
PYTHONPATH=src python3 -m snowl_mobile plan configs/runs/autoglm_androidworld.yml
PYTHONPATH=src python3 -m snowl_mobile run configs/runs/autoglm_androidworld.yml --device-mode existing_device --adb-serial emulator-5554 --output-dir /tmp/snowl-mobile-open-autoglm-androidworld-full
PYTHONPATH=src python3 -m snowl_mobile summarize /tmp/snowl-mobile-open-autoglm-androidworld-full
```

Long-run notes:

- Keep `SNOWL_ANDROIDWORLD_CHECKPOINT_DIR` and `SNOWL_ANDROIDWORLD_OUTPUT_PATH` blank unless you want the bridge to copy those upstream outputs into each trial's raw artifacts.
- Watch `run.log`, `summary.json`, and `events.jsonl` for progress.
- Start with the smoke overrides first; if that path is not stable, the full run will mostly multiply the same failure mode across the suite.

## Mobile-Agent-E Pair

The repository now also includes:

- `configs/runs/mobile_agent_e_androidworld.yml`

Current checkout behavior:

- the checked-in config defaults to the current full `android_world` family, which is `148` planned trials in this checkout
- the same config can be switched to a smoke run with env overrides such as `SNOWL_ANDROIDWORLD_SUITE_FAMILY=android` and `SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend`
- the config reuses the same `mobile_agent_e__androidworld` bridge, `existing_device`, and `standard` artifact level

Suggested commands:

```bash
SNOWL_ANDROIDWORLD_SUITE_FAMILY=android SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend PYTHONPATH=src python3 -m snowl_mobile validate-config configs/runs/mobile_agent_e_androidworld.yml
SNOWL_ANDROIDWORLD_SUITE_FAMILY=android SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend PYTHONPATH=src python3 -m snowl_mobile plan configs/runs/mobile_agent_e_androidworld.yml
SNOWL_ANDROIDWORLD_SUITE_FAMILY=android SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend PYTHONPATH=src python3 -m snowl_mobile run configs/runs/mobile_agent_e_androidworld.yml --device-mode existing_device --adb-serial emulator-5554 --output-dir /tmp/snowl-mobile-mobile-agent-e-androidworld
PYTHONPATH=src python3 -m snowl_mobile summarize /tmp/snowl-mobile-mobile-agent-e-androidworld
```

Full-suite commands:

```bash
PYTHONPATH=src python3 -m snowl_mobile validate-config configs/runs/mobile_agent_e_androidworld.yml
PYTHONPATH=src python3 -m snowl_mobile plan configs/runs/mobile_agent_e_androidworld.yml
PYTHONPATH=src python3 -m snowl_mobile run configs/runs/mobile_agent_e_androidworld.yml --device-mode existing_device --adb-serial emulator-5554 --output-dir /tmp/snowl-mobile-mobile-agent-e-androidworld-full
PYTHONPATH=src python3 -m snowl_mobile summarize /tmp/snowl-mobile-mobile-agent-e-androidworld-full
```

Key artifact paths:

- `trials/<trial_id>/score.json`
- `trials/<trial_id>/trajectory.json`
- `trials/<trial_id>/raw/mobile_agent_e_androidworld/bridge_request.json`
- `trials/<trial_id>/raw/mobile_agent_e_androidworld/final_result.json`
- `trials/<trial_id>/raw/mobile_agent_e_androidworld/steps/0001.console.txt`
- `trials/<trial_id>/raw/mobile_agent_e/runner_result.json`

## Mobile-Agent-v3.5 Pair

The repository now also includes:

- `configs/runs/mobile_agent_v3_5_androidworld.yml`

Current checkout behavior:

- the checked-in config defaults to the current full `android_world` family, which is `148` planned trials in this checkout
- the same config can be switched to a smoke run with env overrides such as `SNOWL_ANDROIDWORLD_SUITE_FAMILY=android` and `SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend`
- the config reuses the same `mobile_agent_v3_5__androidworld` bridge, `existing_device`, and `standard` artifact level

Suggested commands:

```bash
SNOWL_ANDROIDWORLD_SUITE_FAMILY=android SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend PYTHONPATH=src python3 -m snowl_mobile validate-config configs/runs/mobile_agent_v3_5_androidworld.yml
SNOWL_ANDROIDWORLD_SUITE_FAMILY=android SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend PYTHONPATH=src python3 -m snowl_mobile plan configs/runs/mobile_agent_v3_5_androidworld.yml
SNOWL_ANDROIDWORLD_SUITE_FAMILY=android SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend PYTHONPATH=src python3 -m snowl_mobile run configs/runs/mobile_agent_v3_5_androidworld.yml --device-mode existing_device --adb-serial emulator-5554 --output-dir /tmp/snowl-mobile-mobile-agent-v3-5-androidworld
PYTHONPATH=src python3 -m snowl_mobile summarize /tmp/snowl-mobile-mobile-agent-v3-5-androidworld
```

Full-suite commands:

```bash
PYTHONPATH=src python3 -m snowl_mobile validate-config configs/runs/mobile_agent_v3_5_androidworld.yml
PYTHONPATH=src python3 -m snowl_mobile plan configs/runs/mobile_agent_v3_5_androidworld.yml
PYTHONPATH=src python3 -m snowl_mobile run configs/runs/mobile_agent_v3_5_androidworld.yml --device-mode existing_device --adb-serial emulator-5554 --output-dir /tmp/snowl-mobile-mobile-agent-v3-5-androidworld-full
PYTHONPATH=src python3 -m snowl_mobile summarize /tmp/snowl-mobile-mobile-agent-v3-5-androidworld-full
```

Key artifact paths:

- `trials/<trial_id>/score.json`
- `trials/<trial_id>/trajectory.json`
- `trials/<trial_id>/raw/mobile_agent_v3_5_androidworld/bridge_request.json`
- `trials/<trial_id>/raw/mobile_agent_v3_5_androidworld/final_result.json`
- `trials/<trial_id>/raw/mobile_agent_v3_5_androidworld/steps/0001.console.txt`
- `trials/<trial_id>/raw/mobile_agent_v3_5/runner_result.json`
