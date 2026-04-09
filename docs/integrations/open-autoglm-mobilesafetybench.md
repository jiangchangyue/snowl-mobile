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
- `existing_device` mode with `batch_size=1`
- one-device, batch_size=1 full-run config flow
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

The CLI now auto-loads `.env` and `.env.local` from the current working directory, so you can usually just keep these values in `.env.local`.

Because the current real-pair path is `in_process`, the Python environment that runs
`snowl-mobile run` must also be able to import both upstream repos. In practice, install at least:

- `pip install -r references/agents/Open-AutoGLM/requirements.txt`
- `pip install -r references/benchmarks/mobilesafetybench/requirements.txt`

The recommended minimal config now defaults `models[0].id` and `agents[0].model_ref` from `PHONE_AGENT_MODEL`, so switching models usually does not require editing YAML.

The checked-in run config now defaults to `task_source.selector = all`. If you want a smaller smoke run first, set:

- `SNOWL_TASK_SELECTOR='task_category=text_message_sending,task_id=high_risk_001,limit=1'`

`limit=-1` also means no limit.

## Recommended Commands

```bash
PYTHONPATH=src python3 -m snowl_mobile validate-config configs/runs/autoglm_mobilesafetybench.yml
PYTHONPATH=src python3 -m snowl_mobile plan configs/runs/autoglm_mobilesafetybench.yml
PYTHONPATH=src python3 -m snowl_mobile devices list --config configs/runs/autoglm_mobilesafetybench.yml --device-mode existing_device
PYTHONPATH=src python3 -m snowl_mobile devices health-check --config configs/runs/autoglm_mobilesafetybench.yml --device-mode existing_device
PYTHONPATH=src python3 -m snowl_mobile run configs/runs/autoglm_mobilesafetybench.yml --device-mode existing_device --adb-serial emulator-5554 --output-dir /tmp/snowl-mobile-real-pair
PYTHONPATH=src python3 -m snowl_mobile summarize /tmp/snowl-mobile-real-pair
```

`--output-dir` is the real run directory. Reusing the same path resumes the run automatically and skips trials that already finished.

## Known Limits

- current real-pair path is `in_process` bridge execution, not isolated worker execution
- `existing_device` is the primary supported mode; `managed_avd` is not the recommended path for this first real closure
- `batch_size > 1` is out of scope for this phase
- the bridge currently uses heuristic mapping from `finish(message=...)` to MobileSafetyBench evaluator tokens
- the bridge imports `phone_agent` and `mobile_safety` directly from the local checkouts, so upstream Python dependencies must be installed in the same environment as `snowl-mobile`
- if Appium bootstrap, adb control, or the model endpoint fails, the run should fail fast with platform-level diagnostics, but automatic recovery is still minimal

## Artifact Notes

- `score.json` is the platform-facing MobileSafetyBench evaluation result for a single task
- `trajectory.json` is intentionally concise and user-facing; it keeps the task instruction, Thought, Action, Action Input, summarized observation text, and screenshot/XML paths
- per-step raw model outputs remain under `raw/open_autoglm_mobilesafetybench/steps/*.model_response.{txt,json}` and are linked from `trajectory.json`
- `meta.json` and `runtime_recipe.json` are retained as platform reproducibility files and are mostly useful for debugging or rerunning the same trial contract
- `run.log` and `trial.log` now stream the execution process so you can watch reset, bridge execution, and per-step progress while the run is still active
