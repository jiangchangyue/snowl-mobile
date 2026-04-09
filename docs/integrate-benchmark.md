# 集成 Benchmark 仓库

本文档面向未来用户与 Codex，说明如何把一个新的第三方 Benchmark 仓库接入到 `snowl-mobile`。当前仓库已经包含 `MobileSafetyBench` 这一真实 benchmark 的首个集成示例，但整体工作流仍保持通用。

## 1. 先 clone 到哪里

真实上游 benchmark 仓库默认由用户手动 clone 到固定目录：

- `references/benchmarks/<repo_name>/`

默认工作流里，Codex 只读取、分析和适配这个本地仓库，不负责默认联网 clone。

## 2. 先分析哪些文件

建议至少检查：

- `README*`
- `requirements*.txt`
- `pyproject.toml` / `setup.py` / `setup.cfg`
- 主包目录
- `examples/`
- evaluation / scorer / runner 入口
- task manifest / dataset / scenario 文件
- reset / setup / seeding 相关文件
- observation / action / artifact capture 相关文件

本仓库提供的 benchmark repo inspector 会把这些点位结构化输出：

```bash
PYTHONPATH=src python3 -m snowl_mobile inspect-repo benchmark references/benchmarks/<repo_name>
PYTHONPATH=src python3 -m snowl_mobile integration-checklist benchmark references/benchmarks/<repo_name>
```

## 3. 如何选择 wrap / native / hybrid

- `wrap`：上游 benchmark 已经有现成 runner / evaluation pipeline / scorer，优先 wrap。
- `native`：上游明确暴露 task discovery、step loop、observation、scoring API，可直接原生接入。
- `hybrid`：task discovery 和 scorer 可以复用，但环境控制或 action 执行希望由平台接管。

默认策略仍然是 `wrap-first, native-next`。

## 4. Benchmark adapter contract 的责任边界

推荐结构如下：

1. `list_tasks()`：负责 task discovery。
2. `prepare_trial()`：负责 pre-task setup。
3. `seed_environment()`：负责 benchmark-native 的 environment init/reset。
4. `get_initial_observation()`：负责把 benchmark 观察结果映射到 `ObservationBundle`。
5. `run_entry` / wrap runner：负责真正的 benchmark 执行入口。
6. `capture_native_score()`：负责捕获 benchmark native metrics。
7. `cleanup_trial()`：负责 cleanup。
8. `capture_raw_artifacts()`：负责声明截图/XML/log 等原始产物点位。

映射规范：

- benchmark native metrics 保留在 `ScoreBundle.native_metrics`
- platform metrics 只补 run/trial/worker/device 维度，不覆盖 benchmark native metrics
- `ScoreBundle.primary_metric` 应明确指向一项 platform-facing metric，而不是吞掉 native 明细
- 如果 benchmark 需要少量 benchmark-native 配置，而这些配置又不适合硬塞进通用 `task_source` / `reset_requirements`，现在可以放到 `benchmarks[*].options`
  - 例如 AndroidWorld 当前使用它承载 `suite_family`、`tasks`、`n_task_combinations`、`perform_emulator_setup`、`checkpoint_dir`、`console_port`、`grpc_port`

## 5. 如何生成 scaffold

现在推荐直接生成 benchmark template package，而不是只生成单个 adapter 文件：

```bash
PYTHONPATH=src python3 -m snowl_mobile scaffold-benchmark-package \
  references/benchmarks/<repo_name> \
  <adapter_id> \
  --output-dir examples/integration
```

该命令会生成：

- `adapter.py`
- `register.py`
- `config.example.yml`
- `README.md`
- `contract.json`
- `tests/test_<adapter_id>_integration.py`

模板中会保留显式 TODO，指导 Codex 在未来分析真实仓库后补齐：

- task discovery 入口
- environment init/reset 入口
- run entry
- scorer/evaluation 入口
- observation form
- action execution path
- raw artifact capture 点位

## 6. 如何注册到平台

至少需要：

1. 在合适的 registry 初始化位置注册新的 benchmark adapter。
2. 添加一个最小示例配置，绑定至少一个本地 agent。
3. 添加最小 smoke integration test。
4. 保持生成的 `contract.json` 与实际实现一致。

## 7. 如何做最小验证

建议按这个顺序：

1. `validate-config`
2. `plan`
3. `dry-run`
4. benchmark-specific smoke integration test

在真实 emulator / ADB 逻辑进入前，先把 task discovery、reset contract、scorer contract 和 raw artifact capture 点位立稳。

## 8. Concrete Example: MobileSafetyBench

The repository now includes a real benchmark integration example for `MobileSafetyBench`.

See:

- `references/benchmarks/mobilesafetybench/`
- `configs/runs/autoglm_mobilesafetybench.yml`
- `docs/integrations/mobilesafetybench.md`

The key point is that the workflow did not change:

1. the user manually placed the upstream repo under `references/benchmarks/`
2. the platform repo inspector and checklist were used first
3. the adapter was landed with the same benchmark contract and registry flow
4. canonical checked-in config validation still runs through `validate-config / plan / dry-run`

So future real benchmark integrations should still reuse the same inspector, contract, scaffold, checklist, and docs path instead of falling back to one-off scripts.

## 9. Concrete Example: AndroidWorld

The repository now also includes a planning-phase benchmark adapter for `AndroidWorld`.

See:

- `references/benchmarks/android_world/`
- `configs/runs/androidworld_benchmark.yml`
- `docs/integrations/androidworld.md`

Current status:

1. the adapter is registered in the builtin registry
2. task discovery is driven from the real upstream repository structure
3. `validate-config / plan / benchmark-setup / benchmark-run` now work with a checked-in benchmark-side config
4. benchmark-native bootstrap, observation capture, and native scoring now flow into the platform artifact layout
5. the first real pair bridge is intentionally still deferred to a later phase
