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

- `configs/runs/androidworld_benchmark.yml`
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

For multi-emulator AndroidWorld runs, use a distinct gRPC port for each AVD:

```bash
emulator -avd AndroidWorldAvd -no-snapshot -grpc 8554
emulator -avd AndroidWorldAvd2 -no-snapshot -grpc 8555
```

The run CLI still schedules by `--adb-serial`; for existing devices the platform resolves the console port from serials such as `emulator-5562` and discovers the active gRPC port from the running emulator process.

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
- The checked-in real-pair configs now default to the full `android_world` suite, and the canonical documented workflow is the full-run CLI command with explicit model/runtime overrides and one `--adb-serial` per live emulator.
- The checked-in full-suite config is now available, but a real full-suite verification is still pending on a machine that has one interpreter capable of importing both AndroidWorld and Open-AutoGLM dependencies.
- AndroidWorld full runs now inherit the platform's standard same-directory resume behavior: rerunning the same command with the same `--output-dir` skips trials that already have terminal `meta.json + score.json` artifacts. This is trial-level artifact resume, not mid-trial step checkpoint resume.
- The benchmark still recommends a dedicated Python environment for real execution; the platform now lets you point `python_executable` or `ANDROID_WORLD_PYTHON` at that env, but it does not create the environment for you yet.
- `mobile_agent_e x androidworld` is now available through a first minimal pair bridge, but a real full-suite verification is still pending on a machine that has one interpreter capable of importing both AndroidWorld and Mobile-Agent-E dependencies.
- `mobile_agent_v3_5 x androidworld` is now available through a first minimal pair bridge, but a real long-run/full-suite verification is still pending on a machine that has one interpreter capable of importing both AndroidWorld and Mobile-Agent-v3.5 dependencies.

## Canonical Full-Run Commands

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

Key artifact paths for all three paths:

- `trials/<trial_id>/score.json`
- `trials/<trial_id>/trajectory.json`
- `trials/<trial_id>/raw/*_androidworld/bridge_request.json`
- `trials/<trial_id>/raw/*_androidworld/final_result.json`
- `trials/<trial_id>/raw/*/runner_result.json`

Long-run notes:

- keep `SNOWL_ANDROIDWORLD_CHECKPOINT_DIR` and `SNOWL_ANDROIDWORLD_OUTPUT_PATH` blank unless you explicitly want upstream AndroidWorld outputs copied into raw artifacts
- watch `run.log`, `summary.json`, and `events.jsonl` for progress
- resume by rerunning the same command with the same `--output-dir`
