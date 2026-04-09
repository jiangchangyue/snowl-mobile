# MobileSafetyBench Integration

This document records the first real benchmark integration landed in `snowl-mobile`.

Repository path:

- `references/benchmarks/mobilesafetybench/`

The adapter is registered as:

- `mobilesafetybench`

## Repository Analysis

Task discovery entry:

- `asset/tasks/tasks.json`
- Tasks are keyed by `task_category + task_id`
- Each task bundle already contains instruction, initial device state, evaluation criteria, and action-space extensions

Environment init / reset:

- `mobile_safety/environment.py::MobileSafetyEnv.reset`
- `mobile_safety/environment.py::MobileSafetyEnv.set_environment`
- `mobile_safety/component/initializer.py`
- `asset/environments/set_up.py` and `install.sh` are upstream bootstrap scripts for preparing AVD snapshots and installed apps

Scorer / evaluation entry:

- `mobile_safety/evaluator/<task_category>.py::Evaluator`
- `mobile_safety/evaluator/_base_evaluator.py::BaseEvaluator.evaluate`
- The environment calls the evaluator during `MobileSafetyEnv.get_state()`

Observation flow:

- `mobile_safety/component/appium.py::get_viewhierarchy`
- `mobile_safety/component/appium.py::get_screenshot`
- `mobile_safety/agent/utils.py::parse_obs`
- Upstream observations are effectively `image + raw xml/ui tree + parsed text tokens`

Action flow:

- `mobile_safety/component/parser.py::parse_action`
- The parser converts action strings into ADB/Appium operations
- Task-specific evaluator logic then updates goal achievement and harm-prevention state

Recommended integration mode:

- `hybrid`

Reason:

- The repository exposes importable Python surfaces for task data, environment state, and evaluator logic.
- The end-to-end execution loop is still notebook-driven and tightly coupled to upstream agent classes and prompt construction.
- A wrap-first `hybrid` adapter lets `snowl-mobile` reuse upstream benchmark semantics without forcing an early deep refactor.

## Current Adapter Shape

The current adapter intentionally focuses on the stable benchmark-facing parts:

- task discovery from the real upstream manifest
- repository analysis and contract declaration
- mock wrapped single-task run request/result objects
- native metric mapping into `ScoreBundle`
- raw-output persistence into the platform trial artifact directory

Current metric mapping:

- `goal_achievement` stays in `ScoreBundle.native_metrics`
- `harm_prevention` stays in `ScoreBundle.native_metrics`
- `task_success` is mapped dynamically:
  - high-risk task: `harm_prevention`
  - low-risk task: `goal_achievement`

This keeps benchmark-native semantics intact while still giving the platform one primary metric.

## Minimal Validation Path

Canonical checked-in run config:

- `configs/runs/autoglm_mobilesafetybench.yml`

Suggested commands:

```bash
PYTHONPATH=src python3 -m snowl_mobile inspect-repo benchmark references/benchmarks/mobilesafetybench
PYTHONPATH=src python3 -m snowl_mobile validate-config configs/runs/autoglm_mobilesafetybench.yml
PYTHONPATH=src python3 -m snowl_mobile plan configs/runs/autoglm_mobilesafetybench.yml
PYTHONPATH=src python3 -m snowl_mobile dry-run configs/runs/autoglm_mobilesafetybench.yml --output-dir /tmp/snowl-mobile-msb
```

## Current Limitations

- The adapter is real for task discovery and metric mapping, but the wrapped execution path is only mocked in this phase.
- `run` is not yet wired to a real `MobileSafetyEnv` plus external agent loop through the orchestrator.
- The adapter does not yet import or drive upstream built-in agents such as GPT/Claude/Gemini classes.
- Real emulator reset, Appium session creation, and upstream logger replay still depend on a later runtime phase.
- Pair-specific glue is now exercised by the first real pair `Open-AutoGLM x MobileSafetyBench`; future external agents will likely still need their own bridge adapters instead of reusing this pair glue.

## Known Issues

- The upstream top-level execution entry is a notebook (`experiment/evaluate.ipynb`), not a clean CLI module. This is one reason the first integration is `hybrid` rather than pure `wrap`.
- The generic benchmark inspector still suggests `wrap` for the repo, which is a safe default. The final adapter upgrades that recommendation to `hybrid` after manual file-level analysis.
- The repository path appears in user notes with both `MobileSafetyBench` and `mobilesafetybench`; the adapter now tolerates both, but the actual local checkout in this workspace is lower-case.
