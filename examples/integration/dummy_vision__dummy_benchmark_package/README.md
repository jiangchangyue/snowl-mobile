# dummy_vision__dummy_benchmark Bridge Integration Scaffold

This scaffold is for the pair `dummy_vision_agent x dummy_benchmark`.

## When to use this bridge

- the agent and benchmark share a pair-specific observation or action schema
- the pair needs a custom run entry or environment handshake
- the pair needs dedicated ports, launch hints, or side-channel artifacts
- the generic agent and benchmark adapters are individually valid but the pair still needs glue code

## Responsibility boundaries

- observation mapping: pair-only remapping before the bridge run entry
- action mapping: pair-only remapping before benchmark execution
- environment handshake: pair-only bootstrap for env vars, ports, sidecars, or launch hints
- artifact capture: pair-only traces that neither the generic agent nor benchmark adapter owns

## Pair runtime recipe

Use `pair_runtime_recipe.example.yml` as the project-config fragment for this pair.

TODO:

- replace `TODO_observation_mapping_entry`
- replace `TODO_action_mapping_entry`
- replace `TODO_run_entry`
- replace `TODO_environment_handshake_entry`
- replace `TODO_artifact_capture_hook`
- register the bridge
- add a pair-specific smoke validation path
