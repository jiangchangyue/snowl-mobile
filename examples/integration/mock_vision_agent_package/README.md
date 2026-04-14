# Mock Vision Agent Agent Integration Scaffold

This scaffold package was generated from the local agent repository at `references/agents/mock-agent-repo`.

## Suggested integration mode

- `hybrid`

## Capability declaration summary

- capability profile: `vision-capable`
- input modalities: `text, image`
- action output schema: `json_action`
- supported model protocols: `openai_chat`
- tool backends: `adb, appium`
- human confirmation mode: `mock_agent/confirmation_gate.py`
- raw output capture points: `mock_agent/raw_capture.py`

## Recommended responsibility boundaries

- observation transform: `examples/run_demo.py`
- step entry: `examples/run_demo.py`
- run entry: `examples/run_demo.py`
- action normalization: `mock_agent/action_parser.py`
- model call entry: `mock_agent/model_client.py`
- device control entry: `mock_agent/device_controller.py`

## Model compatibility guidance

- declare required modalities explicitly
- keep `supported_model_protocols` aligned with the upstream model client
- use `requires_tool_calling` and `requires_json_mode` only when the agent truly depends on them
- preserve raw model output capture separately from normalized action records

TODO:

- verify the real observation transform path
- verify the actual model-call entry and supported API style
- verify the action normalization schema
- verify whether the agent requires human confirmation
- register the adapter
- replace dummy benchmark bindings in `config.example.yml`
- wire a real smoke integration test
