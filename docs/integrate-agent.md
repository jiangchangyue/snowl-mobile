# 集成 Agent 仓库

本文档面向未来用户与 Codex，说明如何把一个新的第三方 Agent 仓库接入到 `snowl-mobile`。当前仓库已经以 `Open-AutoGLM` 作为第一个真实 agent 走通了这条产品化路径，但这里仍然描述通用方法，而不是只为单个仓库硬编码。

## 1. 先 clone 到哪里

真实上游 agent 仓库默认由用户手动 clone 到固定目录：

- `references/agents/<repo_name>/`

默认工作流里，Codex 只读取、分析和适配这个本地仓库，不负责默认联网 clone。

## 2. 先分析哪些文件

建议至少检查：

- `README*`
- `requirements*.txt`
- `pyproject.toml` / `setup.py` / `setup.cfg`
- 主包目录
- `examples/`
- `cli.py` / `main.py` / `run*.py` / `__main__.py`
- 模型调用入口，例如 client / llm / inference / prompt 相关文件
- 设备控制入口，例如 adb / appium / controller / backend 相关文件
- action parser / output normalizer / transcript / raw log capture 相关文件

本仓库提供的 agent repo inspector 会把这些点位结构化输出：

```bash
PYTHONPATH=src python3 -m snowl_mobile inspect-repo agent references/agents/<repo_name>
PYTHONPATH=src python3 -m snowl_mobile integration-checklist agent references/agents/<repo_name>
```

## 3. 如何选择 wrap / native / hybrid

- `wrap`：上游更像 CLI runner，或者包 API 不稳定，先用外部 runner 包装。
- `native`：上游暴露了清晰、可复用的 Python API，适合直接接入 observation -> step loop。
- `hybrid`：上游既有 importable package，也有脚本/runner；模型调用、解析或设备控制可局部复用。

默认策略仍然是 `wrap-first, native-next`。

## 4. Agent adapter contract 的责任边界

推荐结构如下：

1. `describe()`：声明 `AgentSpec`、能力、模型兼容性约束。
2. `transform_observation()`：负责把上游 observation 变换为 `ObservationBundle`。
3. `build_runtime()` / wrap runner：负责 step/run entry，不负责平台调度和落盘。
4. `normalize_action()`：负责把 agent 原始输出规范化为稳定 action schema。
5. `capture_raw_output()`：负责保留原始模型输出、tool trace、转录等审计材料。

兼容性声明建议：

- `supported_modalities` / `required_modalities`：声明模型输入模态要求。
- `supported_model_protocols`：声明兼容的模型协议，例如 `openai_chat`。
- `requires_tool_calling` / `requires_json_mode`：只在 agent 真正强依赖时置为 `true`。
- `supports_image_input` / `supports_tool_calling` / `supports_json_mode`：说明 agent 自身能力，不要和模型能力混淆。

## 5. 如何生成 scaffold

现在推荐直接生成 agent template package，而不是只生成单个 adapter 文件：

```bash
PYTHONPATH=src python3 -m snowl_mobile scaffold-agent-package \
  references/agents/<repo_name> \
  <adapter_id> \
  --output-dir examples/integration \
  --capability-profile auto
```

如果你已经明确知道要先做 text-only 或 vision-capable 版本，也可以显式指定：

```bash
PYTHONPATH=src python3 -m snowl_mobile scaffold-agent-package \
  references/agents/<repo_name> \
  <adapter_id> \
  --output-dir examples/integration \
  --capability-profile text-only

PYTHONPATH=src python3 -m snowl_mobile scaffold-agent-package \
  references/agents/<repo_name> \
  <adapter_id> \
  --output-dir examples/integration \
  --capability-profile vision-capable
```

该命令会生成：

- `adapter.py`
- `register.py`
- `capability.json`
- `config.example.yml`
- `README.md`
- `contract.json`
- `tests/test_<adapter_id>_integration.py`

模板中会保留显式 TODO，指导 Codex 在未来分析真实仓库后补齐：

- observation transform 入口
- step/run 入口
- action normalization 入口
- model call 入口
- device control 入口
- raw output capture 点位
- AgentSpec 与 ModelSpec 兼容性声明

## 6. 如何注册到平台

至少需要：

1. 在合适的 registry 初始化位置注册新的 agent adapter。
2. 添加一个最小示例配置，绑定兼容的 model 和本地 benchmark。
3. 添加最小 smoke integration test。
4. 保持 `capability.json`、`contract.json` 与实际实现一致。

## 7. 如何做最小验证

建议按这个顺序：

1. `validate-config`
2. `plan`
3. `dry-run`
4. agent-specific smoke integration test

在真实设备控制进入前，先把 observation transform、action normalization、model compatibility 和 raw output capture 点位立稳。

## 8. 现在如果以 Open-AutoGLM 为例，应该怎么做

仓库里现在已经有一个真实参考实现：

- 本地 clone 路径：`references/agents/Open-AutoGLM/`
- 平台 adapter id：`open_autoglm`
- 最小配置：[configs/integrations/autoglm/minimal.yml](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/configs/integrations/autoglm/minimal.yml)
- 具体限制与分析：[docs/integrations/open-autoglm.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/integrations/open-autoglm.md)

它的意义不是“以后都按 Open-AutoGLM 特判”，而是作为一个通用参考：未来接入任何真实 agent，仍然优先复用 inspector、capability declaration、contract、scaffold、checklist 和文档，而不是从零开始写一次性 glue code。

## 9. 现在如果以 Mobile-Agent-E 为例，应该怎么看

仓库里现在还有第二个真实参考实现，它已经进入 `wrap-first` 的真实平台驱动阶段：

- 本地 clone 路径：`references/agents/MobileAgent/Mobile-Agent-E/`
- 平台 adapter id：`mobile_agent_e`
- 最小配置：[configs/integrations/mobile_agent_e/minimal.yml](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/configs/integrations/mobile_agent_e/minimal.yml)
- 具体分析与限制：[docs/integrations/mobile-agent-e.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/integrations/mobile-agent-e.md)

它更适合作为“如何接一个 monolithic research runner”的参考：

- 先把 registry / AgentSpec / compatibility / config / dry-run 打通；
- 再把 provider / model / base_url / api_key / caption-perceptor 这些配置映射收敛在平台侧；
- 用平台侧 subprocess runner 去调用上游 `run_single_task()`，而不是要求用户反复改第三方源码；
- 在没有 dedicated pair bridge 之前，先让它通过统一 `run` 流程稳定落盘 raw output / trajectory / score；
- 等 pair bridge 和 worker env 设计明确后，再把这条路径继续原生化；
- 不要为了接入它，反过来破坏已经可跑的 `Open-AutoGLM x MobileSafetyBench` 主路径。

## 10. 现在如果以 Mobile-Agent-v3.5 为例，应该怎么看

仓库里现在还有第三个真实参考实现，它已经进入“wrap-first 可真实执行，并且已经补上最小 pair bridge”的阶段：

- 本地 clone 路径：`references/agents/MobileAgent/Mobile-Agent-v3.5/`
- 平台 adapter id：`mobile_agent_v3_5`
- 最小配置：[configs/integrations/mobile_agent_v3_5/minimal.yml](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/configs/integrations/mobile_agent_v3_5/minimal.yml)
- 具体分析与限制：[docs/integrations/mobile-agent-v3-5.md](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/docs/integrations/mobile-agent-v3-5.md)

它更适合作为“如何先接一个轻量 mobile_use agent surface，先走 wrapped runner，再把 MobileSafetyBench 生命周期收回 pair bridge”的参考：

- 先把 registry / AgentSpec / compatibility / config / dry-run 打通；
- 把 `base_url / api_key / model / adb_path` 的映射仍然收敛在平台 adapter helper 里；
- 当前通过平台 subprocess runner 调用 `mobile_use/`，不要求用户修改第三方源码，也不提前改动 `MobileSafetyBench` 主逻辑；
- 当前不接 `android_world_v3.5/`，而是只围绕 `mobile_use/` 建立最小平台映射；
- 当前已经有 checked-in run config： [configs/runs/mobile_agent_v3_5_mobilesafetybench.yml](/Users/jcy/Documents/Phd/fdu/project/mobile_agent/mobile-eval/snowl-mobile/configs/runs/mobile_agent_v3_5_mobilesafetybench.yml)
- 当前一任务 smoke 与真实长跑统一通过 `SNOWL_TASK_SELECTOR` override 控制，而不是额外维护第二个 run YAML；
- 当前已经有 `mobile_agent_v3_5__mobilesafetybench` pair bridge，把 MobileSafetyBench reset / bootstrap observation / final-state evaluation 收回到了 pair 层；
- 但它仍然是最小闭环，step-by-step evaluator progress 和 dedicated worker env 还没有完全做完。
