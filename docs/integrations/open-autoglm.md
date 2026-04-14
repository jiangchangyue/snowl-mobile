# Open-AutoGLM Integration

This document records the first real agent integration for `Open-AutoGLM` under the platform's wrap-first contract.

## Local repository path

- expected clone path: `references/agents/Open-AutoGLM/`
- optional override env: `OPEN_AUTOGLM_HOME`

## Upstream structure analysis

- observation modality:
  - `text + image`
  - screen state is assembled in `phone_agent/agent.py::PhoneAgent._execute_step`
  - screenshots are injected into OpenAI-style chat messages through `phone_agent/model/client.py::MessageBuilder.create_user_message`
- action output form:
  - single-line pseudo-code such as `do(action="Tap", ...)` and `finish(message="...")`
  - parsed by `phone_agent/actions/handler.py::parse_action`
- model dependency:
  - OpenAI-compatible chat-completions API via `phone_agent/model/client.py::ModelClient.request`
  - model binding is driven by `base_url + model_name + api_key`
- device backend:
  - Android ADB path
  - HarmonyOS HDC path
  - iOS XCTest/WebDriverAgent path
  - platform-facing minimal validated backend in this phase: `adb_appium`

## Recommended integration mode

- `hybrid`

Reasoning:

- the repo exposes importable Python surfaces for prompts, model calls, action parsing, and device control;
- the top-level execution path is still `main.py` and interactive device execution, so a pure native refactor would be premature;
- a wrap-first hybrid adapter lets `snowl-mobile` keep `AgentSpec / ModelSpec / compatibility / artifacts` under platform control without forking upstream runtime logic.

## What is implemented in this phase

- registered adapter id: `open_autoglm`
- capability declaration and model binding declaration
- backend-aware and vision-aware compatibility checks
- action normalization into platform `ActionRecord`
- raw output capture for mock wrapped runs
- canonical checked-in run config: [configs/runs/autoglm_mobilesafetybench.yml](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/configs/runs/autoglm_mobilesafetybench.yml)

## Repository inspection commands

```bash
PYTHONPATH=src python3 -m snowl_mobile inspect-repo agent references/agents/Open-AutoGLM
```

## Canonical user-facing runs

For current end-to-end testing, prefer the checked-in pair configs and pass runtime settings on the CLI. The detailed commands now live in:

- [Open-AutoGLM x MobileSafetyBench](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/integrations/open-autoglm-mobilesafetybench.md)
- [AndroidWorld pair commands](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/integrations/androidworld.md)

## Current limitations

- the adapter currently stops at contract mapping, mock wrapped run, and artifact capture; it does not yet drive a real device through `PhoneAgent.run()`;
- no attempt is made in this phase to install upstream dependencies or launch a real model endpoint;
- runtime isolation is declared through `worker_mode=venv`, but the actual per-agent isolated environment launcher remains the platform's generic shell;
- only the Android-oriented `adb_appium` platform backend is validated end to end in config/plan/dry-run; HDC and iOS capability are declared from upstream analysis but not yet exercised by the platform runtime;
- the first real pair bridge for `Open-AutoGLM x MobileSafetyBench` now exists, and the `run` path can schedule it across multiple existing emulators with `--batch-size` plus repeated `--adb-serial` values. The pair still runs as an `in_process` bridge path. See [docs/integrations/open-autoglm-mobilesafetybench.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/integrations/open-autoglm-mobilesafetybench.md).
