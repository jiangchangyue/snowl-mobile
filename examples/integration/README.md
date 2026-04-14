# Integration Toolkit Demo

This directory holds generated examples produced from the local mock repositories under `references/`.

Recommended demo flow:

```bash
PYTHONPATH=src python3 -m snowl_mobile inspect-repo agent references/agents/mock-agent-repo
PYTHONPATH=src python3 -m snowl_mobile inspect-repo benchmark references/benchmarks/mock-benchmark-repo
PYTHONPATH=src python3 -m snowl_mobile scaffold-adapter agent references/agents/mock-agent-repo mock_agent_repo --output examples/integration/mock_agent_repo_adapter.py
PYTHONPATH=src python3 -m snowl_mobile scaffold-adapter benchmark references/benchmarks/mock-benchmark-repo mock_benchmark_repo --output examples/integration/mock_benchmark_repo_adapter.py
PYTHONPATH=src python3 -m snowl_mobile scaffold-agent-package references/agents/mock-agent-repo mock_text_agent --output-dir examples/integration --capability-profile text-only
PYTHONPATH=src python3 -m snowl_mobile scaffold-agent-package references/agents/mock-agent-repo mock_vision_agent --output-dir examples/integration --capability-profile vision-capable
PYTHONPATH=src python3 -m snowl_mobile scaffold-benchmark-package references/benchmarks/mock-benchmark-repo mock_benchmark_repo --output-dir examples/integration
PYTHONPATH=src python3 -m snowl_mobile scaffold-bridge-package dummy_vision__dummy_benchmark --agent-id dummy_vision_agent --benchmark-id dummy_benchmark --output-dir examples/integration --integration-mode hybrid --requires-pair-recipe
```
