# Troubleshooting

## `registry list-agents` or `registry list-benchmarks` does not show the expected adapter

Check:

- you are running the current local checkout
- the package is installed from this repo or `PYTHONPATH=src` is set
- builtin registry commands succeed:

```bash
snowl-mobile registry summary
```

Expected current real entries include:

- `mobile_agent_v3_5`
- `mobile_agent_e`
- `open_autoglm`
- `mobilesafetybench`
- `open_autoglm__mobilesafetybench`

## `pip install -e .` fails in a fresh environment

Try:

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
```

If you are temporarily offline, use the source-tree fallback instead:

```bash
PYTHONPATH=src python3 -m snowl_mobile --help
```

## `devices list` returns no devices

Check:

- the emulator is already started manually
- `adb devices` shows an `emulator-<port>` entry
- you are using `--device-mode existing_device`
- if needed, pass `--adb-serial emulator-5554`

## `run` fails with missing environment variables

The current real pair bridge requires:

- `PHONE_AGENT_BASE_URL`
- `PHONE_AGENT_API_KEY`
- `APPIUM_BIN` only if `appium` is not already on `PATH`

The CLI no longer auto-loads `.env.local`, and the repository no longer relies on checked-in `.env.*` files. Either export these in your shell yourself or pass `--base-url`, `--api-key`, and `--model-name` directly to `snowl-mobile run`.

If you copy a multi-line shell command, the trailing `\` must be the final character on the line. A line ending like `\\ ` with a space after the backslash breaks continuation in `zsh` and causes errors such as `snowl-mobile: error: unrecognized arguments:` or `zsh: command not found: --max-steps`.

For the current real Mobile-Agent-E x MobileSafetyBench pair path, also check:

- `MOBILE_AGENT_E_HOME`
- `PHONE_AGENT_BASE_URL` / `PHONE_AGENT_API_KEY`, or Mobile-Agent-E-specific overrides
- `MOBILE_AGENT_E_CAPTION_API_KEY` if you explicitly disable lightweight perception
- Mobile-Agent-E now defaults to lightweight perception for platform runs; set `MOBILE_AGENT_E_LIGHTWEIGHT_PERCEPTION=0` only if you intentionally want the full OCR/grounding stack. Lightweight mode replaces the upstream OCR/icon localization calls with lightweight empty-result shims so the wrapped loop can continue past perception initialization

For the current real Mobile-Agent-v3.5 wrapped path, also check:

- `MOBILE_AGENT_V3_5_HOME`
- `PHONE_AGENT_BASE_URL` / `PHONE_AGENT_API_KEY`, or Mobile-Agent-v3.5-specific overrides
- `MOBILE_AGENT_V3_5_ADB_PATH` if the CLI cannot see the emulator through the default `adb`
- `openai`, `pillow`, and `numpy` installed in the active Python environment

## `run` fails with import errors for `phone_agent`, `mobile_safety`, or `inference_agent_E`

This usually means the upstream dependencies are not installed in the same environment as `snowl-mobile`.

Typical missing packages in the current real pair are:

- `openai`
- `portpicker`
- `modelscope`
- `dashscope`

Install:

```bash
python -m pip install -r references/agents/Open-AutoGLM/requirements.txt
python -m pip install -r references/benchmarks/mobilesafetybench/requirements.txt
python -m pip install -r references/agents/MobileAgent/Mobile-Agent-E/requirements.txt
python -m pip install openai pillow numpy
```

## `run` fails during the real Open-AutoGLM x MobileSafetyBench step loop

The bridge now writes the original traceback and captured upstream diagnostics to:

- `<run_dir>/trials/<trial_id>/raw/open_autoglm_mobilesafetybench/failure.json`

If `summary.json` only shows a generic pair-run failure, inspect `failure.json` first.

## `run` fails during the real Mobile-Agent-E pair run

The pair bridge now writes benchmark-bootstrap diagnostics to:

- `<run_dir>/trials/<trial_id>/raw/mobile_agent_e_mobilesafetybench/bridge_request.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_e_mobilesafetybench/environment_init.console.txt`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_e_mobilesafetybench/failure.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_e_mobilesafetybench/final_result.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_e_mobilesafetybench/steps/0001.console.txt`

The wrapped runner writes launch and failure details to:

- `<run_dir>/trials/<trial_id>/raw/mobile_agent_e/launch_env.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_e/task_payload.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_e/benchmark_context.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_e/runner_request.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_e/runner_result.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_e/reasoning_request_diagnostics.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_e/failure.json`

If the CLI only shows a generic runtime error, inspect `failure.json` first.

If you want the step summaries to appear in the terminal as well as in `trial.log`, rerun with CLI verbosity enabled, for example `snowl-mobile -v run ...` or `PYTHONPATH=src python3 -m snowl_mobile -v run ...`.

Common causes:

- the upstream requirements are not installed in the current Python environment
- the configured API endpoint or API key is invalid
- the emulator serial passed through `--adb-serial` is not visible to `adb`
- the device does not have ADB keyboard style text input support
- the benchmark environment reset or seeding failed before the Mobile-Agent-E subprocess started
- if you explicitly want the full perception path, set `MOBILE_AGENT_E_LIGHTWEIGHT_PERCEPTION=0` in the current shell before retrying; otherwise the platform default remains lightweight perception
- if `trial.log` looks much shorter than the upstream runner transcript, also inspect `raw/mobile_agent_e/runner.stdout.txt`; the pair bridge now reconstructs step summaries into `trial.log` and `raw/mobile_agent_e_mobilesafetybench/steps/*.console.txt`, but the full upstream console stream still lives under `raw/mobile_agent_e/`

For long Mobile-Agent-E full runs, also remember:

- start with the unified config plus `SNOWL_TASK_SELECTOR='task_category=text_message_sending,task_id=low_risk_001,limit=1'` first
- if you use `batch_size > 1`, also pass enough repeated `--adb-serial` values to cover each worker slot
- reuse the same `--output-dir` to resume instead of starting from zero
- expect `raw/mobile_agent_e/` and step artifacts to consume noticeable disk over many tasks

## `run` fails during the real Mobile-Agent-v3.5 x MobileSafetyBench pair run

The pair bridge and wrapped runner write launch and failure details to:

- `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5_mobilesafetybench/bridge_request.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5_mobilesafetybench/environment_init.console.txt`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5_mobilesafetybench/final_result.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5_mobilesafetybench/failure.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5/launch_env.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5/task_payload.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5/benchmark_context.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5/runner_request.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5/runner_result.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5/failure.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5/steps/0001.model_response.txt`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5/steps/0001.model_response.json`

If the CLI only shows a generic runtime error, inspect `failure.json` first.

Common causes:

- the upstream `mobile_use` dependencies are not installed in the current Python environment
- the configured API endpoint or API key is invalid
- the emulator serial passed through `--adb-serial` is not visible to `adb`
- `MOBILE_SAFETY_HOME`, `APPIUM_BIN`, or benchmark-side dependencies are missing, so the pair bridge cannot bootstrap `MobileSafetyEnv`
- the device does not have ADB keyboard style text input support
- the task requires a benchmark-specific app alias that is not covered by the current bridge-owned open-app mapping yet
- evaluator progress is currently reconciled at bootstrap/final-state boundaries because Mobile-Agent-v3.5 does not execute through `MobileSafetyEnv.step()`

For long Mobile-Agent-v3.5 full runs, also remember:

- start with a one-task `SNOWL_TASK_SELECTOR` first
- if you use `batch_size > 1`, also pass enough repeated `--adb-serial` values to cover each worker slot
- reuse the same `--output-dir` to resume instead of starting from zero
- expect both `raw/mobile_agent_v3_5_mobilesafetybench/` and `raw/mobile_agent_v3_5/` to grow noticeably over many tasks
- if the run looks stuck before any trial directory appears, inspect `<run_dir>/run.log`; the current emulator may still be stalling in adb health checks or outer snapshot restore before the pair bridge starts

## `run` fails with `No adb device detected for serial ...`

Check:

- the emulator is already running before `snowl-mobile run`
- `adb devices` shows the exact serial you passed through `--adb-serial`
- if the CLI still cannot see the device for Mobile-Agent-v3.5, set `MOBILE_AGENT_V3_5_ADB_PATH` to the full SDK path, for example `/Users/<you>/Library/Android/sdk/platform-tools/adb`
- if the failure happens immediately after snapshot restore or before the first trial is leased, restart the emulator, recheck `adb devices`, and retry a one-task `SNOWL_TASK_SELECTOR` run first; some emulators still respond poorly to the outer snapshot restore / health-check probes in `existing_device` mode

## `run` fails with `Model error: Mobile-Agent-E reasoning request returned no response`

This usually means the wrapper reached the upstream call site, but the configured endpoint did not return a usable completion.

Check:

- `PHONE_AGENT_BASE_URL` / `PHONE_AGENT_API_KEY`, or Mobile-Agent-E-specific overrides
- TLS / proxy / VPN connectivity to the endpoint
- whether the provider expects a different path suffix such as `/chat/completions`

Then inspect:

- `<run_dir>/trials/<trial_id>/raw/mobile_agent_e/runner.stdout.txt`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_e/reasoning_request_diagnostics.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_e/failure.json`

## A full Mobile-Agent-E run looks stalled

Check:

- `tail -f <run_dir>/run.log`
- `tail -f <run_dir>/trials/<trial_id>/trial.log`
- `<run_dir>/events.jsonl`
- whether the current trial is still writing under `<run_dir>/trials/<trial_id>/raw/mobile_agent_e/`
- whether `<run_dir>/trials/<trial_id>/steps/` is receiving new `*.jpg|xml` files step by step
- on macOS, if `run_dir` was passed under `/tmp/...`, the same files are visible under `/private/tmp/...`
- for full perception runs, also watch `<run_dir>/trials/<trial_id>/raw/mobile_agent_e/runner.stdout.txt`; the first non-lightweight run may spend a long time downloading or loading ModelScope OCR / GroundingDINO assets before `steps.json` appears
- on the current pair bridge, long quiet gaps right after environment initialization usually mean the upstream model/planning call is still in progress; recent builds now emit live progress lines such as "waiting for the first completed step" and "N step(s) have been materialized so far"

If the process was interrupted, rerun the same command with the same `--output-dir`. The platform will resume, reuse completed/skipped trials, and rerun failed or partial ones.

If you need to narrow the problem before rerunning full, temporarily set:

- `SNOWL_TASK_SELECTOR='task_category=text_message_sending,task_id=low_risk_001,limit=1'`
- or target a smaller category slice such as `task_category=social_media_commenting,limit=3`

## A full Mobile-Agent-v3.5 run looks stalled

Check:

- `tail -f <run_dir>/run.log`
- `tail -f <run_dir>/trials/<trial_id>/trial.log`
- `<run_dir>/summary.json`
- `<run_dir>/events.jsonl`
- whether the current trial is writing under `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5_mobilesafetybench/`
- whether the current trial is writing under `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5/`
- on macOS, if `run_dir` was passed under `/tmp/...`, the same files are visible under `/private/tmp/...`

If the process was interrupted, rerun the same command with the same `--output-dir`. The platform will resume, reuse completed/skipped trials, and rerun failed or partial ones.

## `run` fails before finding the benchmark repo

Use the canonical local path:

- `references/benchmarks/mobilesafetybench`
- `references/benchmarks/android_world`

Do not rely on case-insensitive filesystems. A path that appears to work on macOS may fail on Linux if the directory name casing is inconsistent.

## `run` fails with device bootstrap or Appium errors

Check:

- `APPIUM_BIN` points to a valid executable
- the emulator is fully booted
- `adb devices` shows the target serial as `device`
- `snowl-mobile devices health-check --config <config> --device-mode existing_device` reports the device as healthy

## `benchmark-setup` or `benchmark-run` fails for AndroidWorld

Check:

- `ANDROID_WORLD_HOME` points to `references/benchmarks/android_world`
- `ANDROID_WORLD_PYTHON` points to the dedicated environment where AndroidWorld dependencies were installed
- the emulator was launched from the command line with gRPC enabled, for example `emulator -avd AndroidWorldAvd -no-snapshot -grpc 8554`
- `adb devices` shows the target serial
- the `grpc_port` and `console_port` in `configs/runs/androidworld_benchmark.yml` match the real emulator startup
- you ran `benchmark-setup` once before `benchmark-run` on a fresh AndroidWorld emulator, or you are intentionally using `benchmark-run` itself as the first benchmark-side bootstrap path

Inspect:

- `<run_dir>/trials/<trial_id>/raw/androidworld/setup.request.json`
- `<run_dir>/trials/<trial_id>/raw/androidworld/setup.result.json`
- `<run_dir>/trials/<trial_id>/raw/androidworld/setup.stdout.txt`
- `<run_dir>/trials/<trial_id>/raw/androidworld/setup.stderr.txt`
- `<run_dir>/trials/<trial_id>/raw/androidworld/probe.request.json`
- `<run_dir>/trials/<trial_id>/raw/androidworld/probe.result.json`
- `<run_dir>/trials/<trial_id>/raw/androidworld/probe.stdout.txt`
- `<run_dir>/trials/<trial_id>/raw/androidworld/probe.stderr.txt`
- `<run_dir>/trials/<trial_id>/raw/androidworld/failure.json`

Common causes:

- AndroidWorld dependencies were installed into a different Python environment from the one referenced by `ANDROID_WORLD_PYTHON`
- the emulator was started without `-grpc`, so AndroidWorld cannot connect even though `adb devices` looks healthy
- `ANDROID_WORLD_ADB_PATH` points to the wrong `adb` binary
- the configured `console_port` does not match the `emulator-<port>` serial
- `task_success=0` in `score.json` even though the command completed is expected for the current benchmark-only path, because no external agent actions are executed yet

## `run configs/runs/autoglm_androidworld.yml` fails for Open-AutoGLM x AndroidWorld

Check:

- `OPEN_AUTOGLM_HOME` points to `references/agents/Open-AutoGLM`
- `ANDROID_WORLD_HOME` points to `references/benchmarks/android_world`
- `ANDROID_WORLD_PYTHON` points to an interpreter that can import both `phone_agent` and `android_world`
- `PHONE_AGENT_BASE_URL`, `PHONE_AGENT_API_KEY`, and `PHONE_AGENT_MODEL` are all set
- the emulator was launched from the command line with `-grpc`, for example `emulator -avd AndroidWorldAvd -no-snapshot -grpc 8554`
- the emulator is actually Android 13 / API 33; verify `adb -s emulator-5554 shell getprop ro.build.version.sdk` prints `33`
- `adb devices` shows the target serial as `device`
- the direct pair run now performs task-scoped app setup automatically, but `benchmark-setup` is still available as an optional preflight when you want separate AndroidWorld-side diagnostics first

Inspect:

- `<run_dir>/trials/<trial_id>/raw/open_autoglm_androidworld/bridge_request.json`
- `<run_dir>/trials/<trial_id>/raw/open_autoglm_androidworld/bridge_stdout.txt`
- `<run_dir>/trials/<trial_id>/raw/open_autoglm_androidworld/bridge_stderr.txt`
- `<run_dir>/trials/<trial_id>/raw/open_autoglm_androidworld/final_result.json`
- `<run_dir>/trials/<trial_id>/raw/open_autoglm_androidworld/failure.json`
- `<run_dir>/trials/<trial_id>/raw/open_autoglm_androidworld/steps/0001.console.txt`
- `<run_dir>/trials/<trial_id>/raw/open_autoglm_androidworld/steps/0001.model_response.json`

Common causes:

- `ANDROID_WORLD_PYTHON` still points at the wrong environment, so the bridge subprocess cannot import `openai`, `absl`, or other upstream packages
- the emulator was started without `-grpc`, so AndroidWorld bootstrap fails before the first step
- the AVD is API 34 / Android 14 instead of the upstream-recommended API 33 / Android 13, which can make the accessibility forwarder unstable even if the device is named `AndroidWorldAvd`
- the worker interpreter can import both AndroidWorld and Open-AutoGLM, but AndroidWorld task bootstrap still fails because the emulator was not started with the expected gRPC port or the task-specific app setup hit an upstream app issue
- the model endpoint is reachable for MobileSafetyBench runs but `PHONE_AGENT_MODEL` is unset or invalid for the AndroidWorld pair config
- the first bridge keeps action execution on ADB, so upstream launch aliases can still be brittle on some AndroidWorld apps

Newer Open-AutoGLM x AndroidWorld runs also classify two common long-run failures more explicitly:

- `Open-AutoGLM could not reach the configured model endpoint...` means the bridge reached the model call site, but the provider request failed. Check `PHONE_AGENT_BASE_URL`, TLS / proxy / VPN settings, and upstream endpoint health.
- `AndroidWorld failed while installing or refreshing the accessibility forwarder APK...` means AndroidWorld bootstrap hit the forwarder download/install path. Reuse the same prepared emulator when possible; otherwise make sure the worker environment can reach `https://storage.googleapis.com/android_env-tasks/...`.
- `AndroidWorld task-scoped app setup failed while downloading or installing an APK required by the current task...` means a task-specific third-party app such as `clipper` was not yet present on the emulator and the bridge could not fetch it from `https://storage.googleapis.com/gresearch/android_world/...`. Reusing the same prepared emulator now skips re-downloading already-installed task apps.
- `AndroidWorld task bootstrap failed while parsing the device time reported by adb shell date...` means noisy gRPC / adb log lines were mixed into the shell output during upstream datetime setup. Recent bridge builds sanitize that output automatically, so rerun with the updated code and the same emulator / `--output-dir`.

## `run configs/runs/autoglm_androidworld.yml` is too slow, too large, or hard to restart

Check:

- you already stabilized the same config in smoke mode first using `SNOWL_ANDROIDWORLD_SUITE_FAMILY=android` and `SNOWL_ANDROIDWORLD_TASKS=SimpleSmsSend`
- `batch_size` is still `1`; do not raise it yet for AndroidWorld
- the run uses a fresh platform `--output-dir`
- `ANDROID_WORLD_PYTHON` still points to the dedicated environment you used for the smoke run
- `SNOWL_ANDROIDWORLD_CHECKPOINT_DIR` and `SNOWL_ANDROIDWORLD_OUTPUT_PATH` are blank unless you intentionally want upstream outputs copied into every trial artifact directory

Inspect:

- `<run_dir>/run.log`
- `<run_dir>/summary.json`
- `<run_dir>/events.jsonl`
- `<run_dir>/trials/<trial_id>/trial.log`
- `<run_dir>/trials/<trial_id>/raw/open_autoglm_androidworld/failure.json`

Common causes:

- the one-task smoke run was never stable, so the full run simply multiplies the same bridge or environment failure across the whole suite
- `timeout_sec=3600` is still too short for your model endpoint or emulator condition, so long AndroidWorld tasks time out before scoring
- `persist_step_artifacts=true` and copied upstream outputs produce a large artifact tree during long runs
- rerun the same command with the same `--output-dir` to resume; completed trials are skipped automatically, but a partially written trial directory is cleared and rerun from the start

## `run configs/runs/mobile_agent_e_androidworld.yml` fails for Mobile-Agent-E x AndroidWorld

Check:

- `MOBILE_AGENT_E_HOME` points to `references/agents/MobileAgent/Mobile-Agent-E`
- `ANDROID_WORLD_HOME` points to `references/benchmarks/android_world`
- `ANDROID_WORLD_PYTHON` points to an interpreter that can import both `android_world` and `inference_agent_E`
- either `PHONE_AGENT_BASE_URL` and `PHONE_AGENT_API_KEY` are set, or `MOBILE_AGENT_E_BASE_URL` and `MOBILE_AGENT_E_API_KEY` are set
- the emulator was launched from the command line with `-grpc`, for example `emulator -avd AndroidWorldAvd -no-snapshot -grpc 8554`
- the emulator is actually Android 13 / API 33; verify `adb -s emulator-5554 shell getprop ro.build.version.sdk` prints `33`
- `adb devices` shows the target serial as `device`

Inspect:

- `<run_dir>/trials/<trial_id>/raw/mobile_agent_e_androidworld/bridge_request.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_e_androidworld/bridge_stdout.txt`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_e_androidworld/bridge_stderr.txt`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_e_androidworld/final_result.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_e_androidworld/failure.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_e/runner_result.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_e/failure.json`

Common causes:

- `ANDROID_WORLD_PYTHON` still points at the wrong environment, so the bridge subprocess cannot import AndroidWorld or Mobile-Agent-E packages
- the emulator was started without `-grpc`, so AndroidWorld bootstrap fails before Mobile-Agent-E starts
- the AVD is API 34 / Android 14 instead of the upstream-recommended API 33 / Android 13, which can make the accessibility forwarder unstable even if the device is named `AndroidWorldAvd`
- Mobile-Agent-E runtime env mapping fell back to `PHONE_AGENT_*`, but those env vars are unset or point to the wrong endpoint
- the bridge can start, but Mobile-Agent-E still fails inside its own wrapped subprocess; in that case inspect both `raw/mobile_agent_e_androidworld/` and `raw/mobile_agent_e/`
- `Could not get a11y tree` or `AndroidWorld accessibility runtime became unavailable` means AndroidWorld lost its a11y connection during task-scoped setup/bootstrap; restart the emulator, then rerun the same command with the same `--output-dir`
- model-endpoint failures such as repeated `openai.APIConnectionError`, SSL handshake errors, or repeated no-response retries are now treated as fatal infrastructure faults; the run aborts early so you can restore the endpoint and then resume with the same `--output-dir`

Note:

- the AndroidWorld and MobileSafetyBench paths now share the same Mobile-Agent-E lightweight-perception default. If you still see `torch` / `modelscope` import failures during bridge startup, check whether the current shell explicitly set `MOBILE_AGENT_E_LIGHTWEIGHT_PERCEPTION=0`.

## `run configs/runs/mobile_agent_v3_5_androidworld.yml` fails for Mobile-Agent-v3.5 x AndroidWorld

Check:

- `MOBILE_AGENT_V3_5_HOME` points to `references/agents/MobileAgent/Mobile-Agent-v3.5`
- `ANDROID_WORLD_HOME` points to `references/benchmarks/android_world`
- `ANDROID_WORLD_PYTHON` points to an interpreter that can import both `android_world` and the Mobile-Agent-v3.5 runner dependencies
- either `PHONE_AGENT_BASE_URL` and `PHONE_AGENT_API_KEY` are set, or `MOBILE_AGENT_V3_5_BASE_URL` and `MOBILE_AGENT_V3_5_API_KEY` are set
- the emulator was launched from the command line with `-grpc`, for example `emulator -avd AndroidWorldAvd -no-snapshot -grpc 8554`
- the emulator is actually Android 13 / API 33; verify `adb -s emulator-5554 shell getprop ro.build.version.sdk` prints `33`
- `adb devices` shows the target serial as `device`

Inspect:

- `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5_androidworld/bridge_request.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5_androidworld/bridge_stdout.txt`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5_androidworld/bridge_stderr.txt`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5_androidworld/final_result.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5_androidworld/failure.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5/runner_result.json`
- `<run_dir>/trials/<trial_id>/raw/mobile_agent_v3_5/failure.json`

Common causes:

- `ANDROID_WORLD_PYTHON` still points at the wrong environment, so the bridge subprocess cannot import AndroidWorld or Mobile-Agent-v3.5 packages
- the emulator was started without `-grpc`, so AndroidWorld bootstrap fails before Mobile-Agent-v3.5 starts
- the AVD is API 34 / Android 14 instead of the upstream-recommended API 33 / Android 13, which can make the accessibility forwarder unstable even if the device is named `AndroidWorldAvd`
- Mobile-Agent-v3.5 runtime env mapping fell back to `PHONE_AGENT_*`, but those env vars are unset or point to the wrong endpoint
- the bridge can start, but Mobile-Agent-v3.5 still fails inside its own wrapped subprocess; in that case inspect both `raw/mobile_agent_v3_5_androidworld/` and `raw/mobile_agent_v3_5/`
- `Could not get a11y tree` or `AndroidWorld accessibility runtime became unavailable` means AndroidWorld lost its a11y connection during task-scoped setup/bootstrap; restart the emulator, then rerun the same command with the same `--output-dir`
- model-endpoint failures such as repeated `openai.APIConnectionError`, SSL handshake errors, or repeated no-response retries are treated as fatal infrastructure faults; the run aborts early so you can restore the endpoint and then resume with the same `--output-dir`

## `validate-config` fails with model incompatibility

For the first real pair, the model must support:

- text input
- image input
- `api_style = openai_chat`

See:

- `configs/runs/autoglm_mobilesafetybench.yml`

For the current `mobile_agent_e` minimal adapter config, the normalized platform contract is:

- `provider = openai` or `openai_compatible`
- `api_style = openai_chat`
- modalities include both `text` and `image`

See:

- `configs/runs/mobile_agent_e_mobilesafetybench.yml`
- `docs/integrations/mobile-agent-e.md`

For the current `mobile_agent_v3_5` minimal adapter config, the normalized platform contract is:

- `provider = openai` or `openai_compatible`
- `api_style = openai_chat`
- modalities include both `text` and `image`

See:

- `configs/runs/mobile_agent_v3_5_mobilesafetybench.yml`
- `docs/integrations/mobile-agent-v3-5.md`

## The run completed, but you cannot find the results

Check:

- the `Artifacts: ...` path printed by the CLI
- your `--output-dir` directly, because it is the actual run directory
- `summary.json`
- `events.jsonl`
- `trials/<trial_id>/`

## The run stopped early and you want to continue instead of starting from zero

Reuse the same `--output-dir`:

```bash
snowl-mobile run <config>.yml --output-dir /tmp/my-run-dir
```

The platform now resumes automatically from that directory, reuses completed/skipped trials, and reruns failed or partial ones. If you want to rerun just one specific task, delete that trial directory under `trials/` and run the same command again.
