# Mock Benchmark Repo Benchmark Integration Scaffold

This scaffold package was generated from the local benchmark repository at `references/benchmarks/mock-benchmark-repo`.

## Suggested integration mode

- `wrap`

## Recommended responsibility boundaries

- task discovery: `tasks/tasks.json`
- environment init: `reset_env.py`
- pre-task setup: `prepare_trial`
- reset entry: `reset_env.py`
- run entry: `benchmark_runner.py`
- score capture: `scorer.py`
- cleanup: `reset_env.py`
- observation form: `ui_tree`
- action execution path: `action_executor.py`
- raw artifact capture points: `artifact_capture.py`

## Native metrics vs platform metrics

- benchmark-native metric candidate: `TODO_native_metric`
- platform metric target: `task_success`

TODO:

- verify the real task discovery source
- verify the benchmark-native scorer contract
- verify where screenshots/XML/logs can be captured without changing upstream semantics
- register the adapter
- replace dummy agent bindings in `config.example.yml`
- wire a real smoke integration test
