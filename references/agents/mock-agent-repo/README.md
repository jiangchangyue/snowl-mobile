# Mock Agent Repo

This is a local-only mock agent repository used to demonstrate the snowl-mobile integration toolkit.

## Entrypoints

Run the mock agent with:

`python -m mock_agent.cli`

Or inspect the demo flow:

`python examples/run_demo.py`

## What this mock repo exposes

- an importable model client entry via `mock_agent/model_client.py`
- device control helpers using adb/appium wording via `mock_agent/device_controller.py`
- action normalization via `mock_agent/action_parser.py`
- a human confirmation hook via `mock_agent/confirmation_gate.py`
- raw output capture via `mock_agent/raw_capture.py`

The repo intentionally exposes both an importable package and a CLI entrypoint so the inspector can suggest `hybrid` integration mode.
