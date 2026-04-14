# 集成 Pair-Specific Bridge

本文档面向未来用户与 Codex，说明何时应该为某个 `Agent x Benchmark` 组合单独实现 bridge，以及如何把 pair-specific runtime recipe 接进 `snowl-mobile`。

## 1. 什么时候应该用 bridge

只有在“组合级问题”出现时才建议引入 bridge：

- 单独的 agent adapter 和 benchmark adapter 都没有问题，但这对组合仍然跑不起来
- 组合共享特殊 observation mapping / action mapping
- 组合需要特殊 run entry 或 environment handshake
- 组合需要独占端口、launch hints、sidecar 或 pair-only artifact capture

如果问题本质上属于 agent 本身或 benchmark 本身，应该先修普通 adapter，而不是先加 bridge。

## 2. bridge 与普通 adapter 的边界

- `BaseAgentAdapter`：声明 agent 能力与单边 runtime 逻辑
- `BaseBenchmarkAdapter`：声明 benchmark task/reset/scorer/observation 逻辑
- `BaseBridgeAdapter`：只处理某个固定 `agent_id x benchmark_id` 的组合级 glue

推荐把 bridge 的职责限定在：

1. `observation mapping`
2. `action mapping`
3. `run entry`
4. `environment handshake`
5. `artifact capture hooks`

## 3. pair-specific runtime recipe 放在哪里

项目配置中现在可以声明：

```yaml
pair_runtime_recipes:
  - recipe_id: demo_pair_recipe
    agent_id: some_agent
    benchmark_id: some_benchmark
    bridge_id: some_agent__some_benchmark
    requires_bridge: true
    worker_mode: container
    env_isolation: container
    control_backend: adb_appium
    reset_policy: snapshot_then_seed
    backend_requirements: [adb_appium, bridge_runtime]
    required_env: [SOME_ENV_FLAG]
    env_vars:
      SOME_PAIR_MODE: enabled
    ports:
      bridge_port: 51001
    launch_hints:
      handshake: pair.handshake
      run_entry: pair.run
```

这个 schema 不是为了替代普通 runtime recipe，而是为了给某个固定组合做“组合级覆写”。

## 4. 如何生成 bridge scaffold

推荐直接用：

```bash
PYTHONPATH=src python3 -m snowl_mobile scaffold-bridge-package \
  <bridge_id> \
  --agent-id <agent_id> \
  --benchmark-id <benchmark_id> \
  --output-dir examples/integration \
  --integration-mode hybrid \
  --requires-pair-recipe
```

它会生成：

- `bridge.py`
- `register.py`
- `pair_runtime_recipe.example.yml`
- `README.md`
- `contract.json`
- `tests/test_<bridge_id>_bridge.py`

## 5. 如何做最小验证

建议顺序：

1. 确认普通 agent/benchmark adapter 已经能通过基础 validate
2. 加入 bridge 和 pair runtime recipe
3. 运行 `plan`
4. 确认 plan 里能看到 `bridge_id / pair_recipe_id`
5. 再跑 `dry-run` 或 pair-specific smoke test

## 6. 本阶段的边界

本阶段只把 bridge contract、pair runtime recipe schema、planner/compatibility 诊断和 scaffold 路径立住。

不会接任何真实第三方仓库，也不会实现真实 pair runtime。
