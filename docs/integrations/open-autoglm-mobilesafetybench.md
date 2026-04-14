# Open-AutoGLM x MobileSafetyBench

This document tracks the first real pair integration landed in `snowl-mobile`.

## Why A Bridge Is Required

This pair needs a dedicated bridge because the two upstream repos disagree on action ownership:

- `Open-AutoGLM` expects the agent loop to capture the screen, call the model, and execute the action on device.
- `MobileSafetyBench` expects the benchmark environment to own reset, observation capture, evaluator updates, and, in its native loop, action execution.

The pair bridge keeps these boundaries explicit:

- `MobileSafetyBench` owns task discovery, reset, observation capture, and native scoring.
- `Open-AutoGLM` owns model inference, raw output capture, and device-side action execution.
- the bridge maps Open-AutoGLM actions into evaluator-facing MobileSafetyBench action tokens such as `refuse()` and `ask-consent()`.

## What Works In P16

- `validate-config`
- `plan`
- `run`
- `summarize`
- `existing_device` mode with one or more leased emulators
- dynamic multi-emulator scheduling when `--batch-size > 1` and multiple `--adb-serial` values are provided
- pair-specific artifacts under the platform run directory
- user-facing `trajectory.json` plus real-time `run.log` / `trial.log`
- benchmark-aware launch aliases for common MobileSafetyBench apps, so generic Open-AutoGLM `Launch` actions like `Browser`, `Chrome`, `PhotoNote`, `Stock`, `Calendar`, `Bank`, `Maps`, and `Joplin` resolve to the benchmark's expected Android packages

The canonical config is:

- [configs/runs/autoglm_mobilesafetybench.yml](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/configs/runs/autoglm_mobilesafetybench.yml)

## Required Environment

Before a real run, export at least:

- `OPEN_AUTOGLM_HOME`
- `MOBILE_SAFETY_HOME`
- `PHONE_AGENT_BASE_URL`
- `PHONE_AGENT_API_KEY`
- `APPIUM_BIN`

Recommended path values:

- `OPEN_AUTOGLM_HOME=$PWD/references/agents/Open-AutoGLM`
- `MOBILE_SAFETY_HOME=$PWD/references/benchmarks/mobilesafetybench`

The CLI no longer auto-loads `.env` or `.env.local`. Pass endpoint values on the command line or export them in your shell yourself.

Because the current real-pair path is `in_process`, the Python environment that runs
`snowl-mobile run` must also be able to import both upstream repos. In practice, install at least:

- `pip install -r references/agents/Open-AutoGLM/requirements.txt`
- `pip install -r references/benchmarks/mobilesafetybench/requirements.txt`

The checked-in config keeps a stable default model id, and `--model-name` now overrides both `models[0].id` and `agents[0].model_ref` cleanly at run time.

The checked-in run config now defaults to the full MobileSafetyBench task set, and the canonical documented workflow is the full-run CLI command below.

## Recommended Commands

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

`--output-dir` is the real run directory. Reusing the same path resumes the run automatically and skips trials that already finished.

## Known Limits

- current real-pair path is `in_process` bridge execution, not isolated worker execution
- `existing_device` is the primary supported mode; `managed_avd` is not the recommended path for this first real closure
- `batch_size > 1` is supported for `run`, but the pair still shares one host Python environment and one local dependency stack
- the bridge currently uses heuristic mapping from `finish(message=...)` to MobileSafetyBench evaluator tokens
- the bridge imports `phone_agent` and `mobile_safety` directly from the local checkouts, so upstream Python dependencies must be installed in the same environment as `snowl-mobile`
- if Appium bootstrap, adb control, or the model endpoint fails, the run should fail fast with platform-level diagnostics, but automatic recovery is still minimal

## Artifact Notes

- `score.json` is the platform-facing MobileSafetyBench evaluation result for a single task
- `trajectory.json` is intentionally concise and user-facing; it keeps the task instruction, Thought, Action, Action Input, summarized observation text, and screenshot/XML paths
- per-step raw model outputs remain under `raw/open_autoglm_mobilesafetybench/steps/*.model_response.{txt,json}` and are linked from `trajectory.json`
- `meta.json` and `runtime_recipe.json` are retained as platform reproducibility files and are mostly useful for debugging or rerunning the same trial contract
- `run.log` and `trial.log` now stream the execution process so you can watch reset, bridge execution, and per-step progress while the run is still active
