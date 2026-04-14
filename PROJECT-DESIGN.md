# snowl-mobile 项目设计说明书

版本：v0.1  
日期：2026-03-16  
项目代号：**snowl-mobile**  
定位：面向 **Mobile Agent 动态安全评测** 的可扩展编排与执行平台

---

## 1. 文档目的

本文档用于定义 snowl-mobile 的总体目标、系统边界、核心架构、关键抽象、运行机制、插件接口、失败恢复策略、数据产物规范以及分阶段实施方向。该文档面向两类读者：

1. **项目设计与验收者**：用于理解平台应当具备的能力边界、关键设计决策和后续扩展方式。
2. **Codex / 自动编码代理**：用于指导从 0 到 1 的实现过程，避免偏离目标，保证目录结构、接口契约、运行时语义和数据产物格式从一开始就稳定。

本项目不是某一个 Mobile Agent 或某一个 Benchmark 的专用 runner，而是一个 **“编排内核 + 适配层 + 运行时隔离 + 产物系统 + 动态任务合成”** 的平台化工程。

---

## 2. 项目背景与目标

Mobile Agent 相关开源项目越来越多，但当前生态存在几个明显问题：

- 不同 Agent 与 Benchmark 的运行方式彼此割裂；
- 不同仓库对模拟器、ADB、Appium、Python 版本、依赖库要求不一致；
- Benchmark 指标异构，难以做统一调度、统一监控和统一数据沉淀；
- 缺乏一个可扩展的平台，来系统地保存轨迹、截图、XML、动作、错误、评分等完整研究数据；
- 新的 Agent 或 Benchmark 接入门槛高，复用困难；
- 安全测试用例的合成通常散落在单独脚本里，缺少可复用的“任务合成 -> 执行 -> 评分”闭环。

### 2.1 核心目标

snowl-mobile 的核心目标如下：

1. **统一运行入口**  
   用户可以选择任意已接入的 Mobile Agent、任意已接入的 Benchmark、任意允许绑定的基座模型，在本地或服务器上的 Android 模拟器集群上并行执行评测。

2. **统一编排内核**  
   平台负责 Trial 计划展开、资源分配、模拟器调度、失败重试、设备重置、任务执行、评分收集、指标聚合和产物归档。

3. **统一插件式扩展**  
   平台对 Agent、Benchmark、Model、Device Backend、Reset Strategy、Scorer、Synthesis Pipeline 暴露稳定的注册接口与适配契约。

4. **完整轨迹数据沉淀**  
   每个 Trial / Task 都能够保存完整执行轨迹，包括 screenshot、XML、Observation、Thought/Action、执行结果、日志、错误栈、评分明细等。

5. **可复现实验运行**  
   通过 Project Spec、Runtime Recipe、Manifest、Seed、Snapshot 等机制，尽可能保证同一批运行具有可复现性。

6. **可支撑动态安全任务合成**  
   支持根据自然语言规则文档，自动构造安全测试场景、前置环境、任务集和评分规则映射，并输出为平台原生 benchmark 包。

### 2.2 非目标

为避免实现初期失焦，以下内容不作为 v0.x 阶段的强制目标：

- 不追求所有 Agent 都被平台完全“原生重写”；
- 不要求不同 Benchmark 的原始评分标度被强行归一化为单一总分；
- 不在初期支持 iOS 或真实手机设备集群；
- 不在初期自动替用户安装 Android Studio、SDK、系统镜像等大型基础依赖；
- 不在初期提供复杂网页前端；CLI + 轻量本地监控足够。

---

## 3. 设计原则

### 3.1 平台优先，不做脚本拼接

平台必须优先设计为一个长期可维护的系统，而不是把若干上游项目仓库用 shell script 粘起来。  
一切能力都要落到明确的契约上：配置契约、目录契约、接口契约、数据契约、运行契约。

### 3.2 Wrap-first，Native-next

平台初期必须允许快速接入已有仓库。因此适配层应支持：

- **Wrap 模式**：把上游仓库视为黑盒 runner，通过 subprocess、RPC 或 HTTP 进行调用；
- **Native 模式**：平台直接通过统一接口驱动 Agent/Benchmark；
- **Hybrid 模式**：部分环节复用上游代码，部分环节平台原生实现。

### 3.3 模拟器是一级调度资源

Mobile 评测和普通 benchmark 最大不同在于：**模拟器不是被动外设，而是主要稀缺资源之一**。  
因此，模拟器实例、snapshot、reset、health check、restart、回收必须是内核的一等抽象。

### 3.4 环境隔离优于依赖合并

不同 Agent / Benchmark 通常有不同 Python 版本和第三方依赖。平台默认采取：

- Host Engine 环境；
- Worker 独立虚拟环境；
- 必要时容器化运行。

不应试图把所有 requirements 暴力合并进一个环境。

### 3.5 轨迹即资产

平台不只是跑分工具，还要沉淀高价值研究数据。  
因此 artifacts、events、trajectory、observation snapshot 的存储设计必须从第一天就稳定。

### 3.6 失败可恢复，恢复可审计

平台必须对模型调用失败、模拟器卡死、ADB 断连、Agent 解析异常、Benchmark 运行异常等情况提供：

- 分类化错误码；
- 重试策略；
- 恢复策略；
- 可审计日志。

---

## 4. 总体架构

## 4.1 核心架构图

```text
┌────────────────────────────────────────────────────────────────────┐
│                           User / CLI / Config                     │
│                     project.yml / run command                     │
└───────────────────────────────┬────────────────────────────────────┘
                                │
                                v
┌────────────────────────────────────────────────────────────────────┐
│                         Project Loader / Validator                │
│   parse spec · compatibility check · matrix expansion · plan      │
└───────────────────────────────┬────────────────────────────────────┘
                                │
                                v
┌────────────────────────────────────────────────────────────────────┐
│                     Orchestration Engine (Core)                   │
│  planner · scheduler · retry controller · lifecycle manager       │
└───────────────┬──────────────────────┬─────────────────────────────┘
                │                      │
                │                      │
                v                      v
┌──────────────────────────┐   ┌─────────────────────────────────────┐
│   Emulator Pool Manager  │   │    Worker Runtime / Adapter Layer   │
│  start · reset · assign  │   │ agent adapters · benchmark adapters │
│  health · restart        │   │ bridge adapters · model bindings    │
└───────────────┬──────────┘   └──────────────────┬──────────────────┘
                │                                  │
                │                                  │
                v                                  v
         ┌───────────────┐                ┌──────────────────────────┐
         │ Android AVDs  │                │ Agent / Benchmark repos  │
         │ adb/appium    │                │ venv / conda / container │
         └───────────────┘                └──────────────────────────┘

                                │
                                v
┌────────────────────────────────────────────────────────────────────┐
│                       Scoring / Aggregation Layer                  │
│ native metrics · platform metrics · summary · live progress       │
└───────────────────────────────┬────────────────────────────────────┘
                                │
                                v
┌────────────────────────────────────────────────────────────────────┐
│                Artifact Store / Event Bus / Monitoring            │
│ runs/ · events.jsonl · trials/ · screenshots · xml · logs        │
└────────────────────────────────────────────────────────────────────┘
```

### 4.2 六层架构划分

1. **Authoring / Config 层**  
   负责用户如何声明一个实验运行，核心产物是 `project.yml`。

2. **Orchestration / Core 层**  
   负责计划展开、兼容性检查、调度、重试、状态流转与生命周期管理。

3. **Adapter 层**  
   负责接入 Agent、Benchmark、Bridge、Model Provider、Reset Strategy 等扩展。

4. **Runtime / Resource 层**  
   负责模拟器池、worker 环境、并发预算、队列、slot 管理。

5. **Artifact / Observability 层**  
   负责日志、事件、轨迹、图片、XML、结果、指标聚合与监控。

6. **Synthesis 层**  
   负责规则文档驱动的动态测试任务合成，输出为平台原生 benchmark 包。

---

## 5. 顶层概念模型

### 5.1 Project

一次完整运行的配置说明。由用户编写 `project.yml` 指定：

- 要运行的 Agent 列表；
- 要运行的 Benchmark 列表；
- 模型绑定；
- 并行度；
- 模拟器配置；
- 失败策略；
- 产物存储级别；
- 输出目录等。

### 5.2 Run

一次实际执行的实验批次。  
Run 从 ProjectSpec 解析而来，具有唯一 `run_id`，包含：

- 固化后的计划；
- 展开后的 Trial 集；
- 调度元数据；
- 汇总指标；
- 事件流；
- artifacts 根目录。

### 5.3 Trial

平台中的最小调度单元。建议定义为：

`Trial = BenchmarkTask × AgentVariant × ModelBinding × Seed × RuntimeRecipe`

Trial 拥有独立生命周期、状态、日志和产物目录，是重试、超时、失败、评分与归档的基本单位。

### 5.4 Agent Variant

同一个 Agent 在不同提示词、不同 action parser、不同模型、不同参数配置下可形成多个 Agent Variant。  
平台不直接把“仓库名”当成 Agent，而是将“可执行的 agent 配置实体”视为 Variant。

### 5.5 Benchmark Task

某个 benchmark 中的一个具体任务实例。  
它至少包括：

- task_id；
- 指令描述；
- 环境初始化需求；
- 终止条件；
- 评分入口。

### 5.6 Runtime Recipe

Runtime Recipe 描述一个 Trial 的完整运行配方。至少包含：

- 使用哪个 Agent 环境；
- 使用哪个 Benchmark 环境；
- 使用什么模拟器 profile；
- 使用什么 reset 策略；
- 使用何种 observation 模态；
- 使用何种 model binding；
- 使用哪个 worker backend。

这个对象是复现与调试的核心。

---

## 6. 运行与调度模型

### 6.1 基本执行流程

1. 读取 `project.yml`
2. 解析并校验 Agent、Benchmark、Model 的兼容性
3. 展开 matrix，生成 Trial 列表
4. 启动 Emulator Pool
5. 将 Trial 放入待执行队列
6. Scheduler 监控可用模拟器槽位和 worker 槽位
7. 分配 Trial 给某个 EmulatorInstance + WorkerRuntime
8. 执行平台级 reset
9. 执行 benchmark-specific 环境注入
10. 运行 Trial 主循环
11. 结束后调用 scorer 获取 native metrics
12. 聚合为 platform metrics
13. 写入 artifacts、events、summary
14. 释放资源并调度下一个 Trial
15. 所有 Trial 完成后输出总结果并自动关停模拟器

### 6.2 调度原则

调度器应遵循以下原则：

- **模拟器优先利用率最大化**：模拟器空闲时立即分配下一个 Trial；
- **资源约束感知**：同时受限于 emulator slots、model provider 并发、worker slots；
- **长短任务混合**：避免简单平均分块导致尾部拖慢；
- **失败隔离**：某个 Trial 失败不应阻塞同一 Run 的其它 Trial；
- **可中断与可恢复**：支持 run-level 停止、resume、skip-failed。

### 6.3 推荐调度策略

建议实现一个分层调度器：

- 第 1 层：全局队列（pending / running / retry / completed）
- 第 2 层：按 `runtime_recipe` 做轻量分组，减少频繁切换环境的成本
- 第 3 层：按模拟器实例的健康状态与最近使用情况调度
- 第 4 层：按 provider 并发配额与速率限制控制模型请求

---

## 7. 模拟器与设备管理设计

### 7.1 基本要求

平台应支持通过 batch_size 自动管理多个 Android 模拟器实例。  
若用户设置 `batch_size = 5`，平台要能够：

- 自动创建 / 选择 5 个 AVD 实例；
- 并行启动；
- 建立 ADB 连接；
- 进行健康检查；
- 任务结束后自动关闭。

### 7.2 设备管理边界

平台负责：

- AVD 选择与实例编号；
- 启动、关闭、重启；
- snapshot 恢复；
- ADB 连接监测；
- 设备空闲/忙碌状态；
- 心跳与健康检查。

Benchmark 负责：

- 某个 task 所需的环境注入；
- 任务相关前置内容，如联系人、短信、文件、账号状态等。

### 7.3 两阶段 reset 策略

推荐采用两阶段 reset：

#### 阶段 A：平台级 baseline reset
恢复到平台维护的干净 snapshot，例如：
- 刚开机且基础依赖已安装；
- ADB 与必要服务可用；
- benchmark 运行前不残留上一个 task 的状态。

#### 阶段 B：benchmark/task-specific seeding
由 BenchmarkAdapter 在 Trial 开始前注入任务需要的状态，如：
- 联系人；
- 短信；
- 邮件；
- 文件；
- 某个 app 的预登录状态；
- 某些页面缓存数据。

这样既能保证跨 Task 不串环境，又不破坏 Benchmark 原有语义。

### 7.4 设备异常处理

设备异常至少分为以下几类：

- ADB disconnected
- emulator process dead
- device boot timeout
- UI dump timeout
- snapshot restore failed
- appium session broken

恢复优先级建议为：

1. 重新执行单步操作；
2. 重连 ADB / 重新初始化控制会话；
3. 恢复 snapshot；
4. 重启模拟器；
5. 标记 Trial 失败并进入 retry 队列。

---

## 8. Observation 与 Action 设计

### 8.1 Observation 不应等同于 Prompt 输入

平台必须保存原始 Observation，而不是只保存给某个 Agent 的“最终 prompt 文本”。  
原因是：

- 不同 Agent 支持不同模态；
- 未来研究可能需要重新构造 prompt；
- 原始 screenshot / XML / UI tree 具有更高复用价值。

### 8.2 ObservationBundle

建议统一定义 `ObservationBundle`，包含：

- `timestamp`
- `screenshot_path`
- `xml_path`
- `ui_tree_json_path`
- `parsed_text`
- `activity`
- `package_name`
- `screen_size`
- `orientation`
- `source_backend`
- `extra`

### 8.3 ObservationTransformer

平台应提供转换器，用于从原始 ObservationBundle 生成不同输入形态：

- text-only observation
- image-only observation
- image + text mixed observation
- benchmark-native observation

### 8.4 ActionRecord

平台需要区分四种动作信息：

1. `agent_raw_output`：Agent 原始生成文本；
2. `parsed_action`：解析器从原始输出中提取出的动作结构；
3. `executed_action`：实际送给设备控制后端执行的动作；
4. `execution_result`：执行后返回的结果或错误。

这样可以完整保存“模型输出 -> 解析 -> 执行”链条。

---

## 9. Agent、Benchmark、Model 的兼容性设计

### 9.1 为什么必须做兼容性校验

不同 Agent 对底座模型和 observation 模态要求不同：

- 某些 Agent 只能接收文本 observation；
- 某些 Agent 必须依赖图像输入；
- 某些 Agent 依赖特定 API 风格，例如 OpenAI-compatible chat completion；
- 某些 Agent 的 parser、tool format、prompt contract 与特定模型强相关。

因此平台不能允许用户随意把任意 Agent 与任意 Model 随意绑定。

### 9.2 AgentSpec 中必须声明的信息

- `supported_modalities`
- `required_modalities`
- `supported_model_protocols`
- `supports_tool_calling`
- `supports_image_input`
- `supports_json_mode`
- `action_schema`
- `prompt_contract_version`
- `worker_mode`

### 9.3 CompatibilityResolver

平台应在 Run 开始前通过 `CompatibilityResolver` 检查：

- Agent 与 Model 是否兼容；
- Agent 与 Benchmark 是否兼容；
- Benchmark 与 Device Backend 是否兼容；
- Runtime Recipe 是否可构造；
- observation / action contract 是否匹配。

不兼容应在计划阶段 fail-fast，而不是运行到中间才崩。

---

## 10. 环境隔离与运行时设计

### 10.1 问题来源

不同上游仓库可能要求：

- Python 3.10 / 3.11 / 3.12；
- 不同版本的 Appium 客户端；
- 不同版本的 openai / transformers / adb 相关依赖；
- 自定义 shell 命令、环境变量或路径结构。

因此平台不能假设所有 Agent 和 Benchmark 能在同一个 Python 环境里运行。

### 10.2 三种 worker 模式

#### 1) in_process
适用于平台原生、小依赖的 adapter。  
优点：简单、开销低。  
缺点：最容易被依赖冲突污染。

#### 2) venv/conda worker
每个 adapter 在独立环境里运行，通过 RPC/stdio 与 host engine 通信。  
这是默认推荐模式。

#### 3) containerized worker
适用于重依赖、系统依赖复杂或冲突严重的项目。  
例如某些 benchmark 或模拟器辅助工具可封装为容器侧 worker。

### 10.3 RuntimeBridge

建议定义 RuntimeBridge 协议，负责 engine 与 worker 的通信，包括：

- create session
- send observation
- get next action
- send step result
- get final outputs
- abort / cleanup

---

## 11. 评分与结果聚合设计

### 11.1 原则

平台必须保留 benchmark 原生评分语义，不能粗暴地把不同 benchmark 的结果压扁成一个“统一总分”。

### 11.2 ScoreBundle 结构

建议定义：

- `native_metrics`：benchmark 原生输出，如 success/fail、安全违规标签、多维得分等；
- `primary_metric`：该 benchmark 推荐展示的主指标；
- `platform_metrics`：跨 benchmark 通用指标。

### 11.3 建议的 platform metrics

- `trial_status`
- `runtime_sec`
- `step_count`
- `retry_count`
- `emulator_restart_count`
- `model_error_count`
- `observation_mode`
- `artifact_bytes`
- `terminated_by`
- `task_completed`

### 11.4 实时展示

平台应支持实时显示：

- 总 Trial 数 / 已完成 / 失败 / 重试中；
- 当前运行中的任务；
- 每个 Agent × Benchmark 组合的完成进度；
- 已完成 Trial 的 primary metric 均值；
- 失败原因分布。

---

## 12. 轨迹、日志与产物存储设计

### 12.1 基本要求

每个 Trial 都应作为独立目录存储，避免将所有数据写入一个巨型 JSON 文件。

### 12.2 推荐目录结构

```text
runs/<run_id>/
  manifest.json
  project.snapshot.yml
  plan.json
  summary.json
  metrics_wide.csv
  events.jsonl
  trials/
    <trial_id>/
      meta.json
      runtime_recipe.json
      score.json
      trajectory.json
      stderr.log
      stdout.log
      steps/
        0001.png
        0001.xml
        0001.obs.json
        0001.action.json
        0002.png
        ...
```

### 12.3 trajectory.json 设计建议

每一行对应一步，包含：

- `step_id`
- `timestamp_start`
- `timestamp_end`
- `observation_ref`
- `agent_raw_output_ref`
- `parsed_action_ref`
- `executed_action_ref`
- `result_ref`
- `latency_ms`
- `error_type`
- `notes`

### 12.4 Artifact Level

建议支持三级产物保存策略：

- `light`：只保存关键日志和分数；
- `standard`：保存截图、XML、动作、trajectory；
- `full`：在 standard 基础上保存中间 prompt、模型响应、额外调试信息。

---

## 13. 插件系统与集成规范

### 13.1 插件类别

平台建议支持以下注册类别：

- Agent Adapter
- Benchmark Adapter
- Bridge Adapter
- Model Provider
- Device Backend
- Reset Strategy
- Scorer
- Observation Transformer
- Synthesis Generator

### 13.2 Agent Adapter 统一接口

建议最小接口如下：

- `describe() -> AgentSpec`
- `build_runtime(...)`
- `create_session(...)`
- `step(observation_bundle) -> AgentStepOutput`
- `close_session(...)`

对于 wrap 模式，可以允许：

- `run_trial(trial_context) -> TrialResult`

### 13.3 Benchmark Adapter 统一接口

建议最小接口如下：

- `describe() -> BenchmarkSpec`
- `list_tasks(...)`
- `prepare_trial(...)`
- `seed_environment(...)`
- `get_initial_observation(...)`
- `apply_action(...)`
- `is_terminated(...)`
- `score_trial(...)`
- `cleanup_trial(...)`

### 13.4 Bridge Adapter 的必要性

某些上游项目的 Agent 与 Benchmark 是强耦合设计，拆开成本高。  
因此平台应允许声明一个 pair-specific 的 Bridge Adapter，例如：

- `autoglm__mobilesafetybench`
- `mobileagent__androidworld`

其职责是优先保证“可运行”，后续再逐步拆解为独立 Agent Adapter + Benchmark Adapter。

---

## 14. 动态安全任务合成子系统

### 14.1 目标

用户输入：

- 一份规则文档；
- 一个待测 Agent；
- 一组生成参数；

平台输出：

- 一批安全测试任务；
- 每个任务的情景说明；
- 前置环境注入脚本或 seed；
- 可执行任务数据；
- 对应评分规则映射。

### 14.2 建议拆分为四段流水线

1. **Rule Parsing**  
   解析规则文档，抽取实体、约束、禁止行为、边界条件。

2. **Scenario Synthesis**  
   生成真实且合理的用户使用情景，例如聊天、转账、上传文件、读取短信、相册操作等。

3. **Task Materialization**  
   将情景转化为具体任务实例，定义前置状态、目标、终止条件和期望风险。

4. **Environment Seeding**  
   生成联系人、短信、相册图片、文件、App 状态等初始化注入信息。

### 14.3 合成输出格式

动态合成系统不应直接“边生成边跑”，而应输出为平台原生 benchmark 包，例如：

```text
generated_benchmarks/<bench_id>/
  benchmark.yaml
  tasks/
  seeds/
  scorer.py
  metadata.json
```

这样主引擎可以把它当作普通 benchmark 来运行。

---

## 15. 关键核心类设计

以下为推荐的核心类清单。类名可随实现调整，但职责不应漂移。

## 15.1 ProjectSpec

**职责**：承载用户声明的实验配置。  
**关键属性**：
- `project_name`
- `agents`
- `benchmarks`
- `models`
- `matrix`
- `runtime`
- `artifacts`
- `retries`
- `monitoring`
- `paths`

**关键方法**：
- `validate()`
- `expand_matrix()`
- `freeze_snapshot()`

## 15.2 AgentSpec

**职责**：描述某个 Agent 的能力与约束。  
**关键属性**：
- `agent_id`
- `display_name`
- `integration_mode`
- `required_modalities`
- `supported_modalities`
- `supported_model_protocols`
- `required_env`
- `action_schema`
- `prompt_contract_version`

**关键方法**：
- `is_model_compatible(model_spec)`
- `is_benchmark_compatible(benchmark_spec)`

## 15.3 ModelSpec

**职责**：描述底座模型及其 API 能力。  
**关键属性**：
- `model_id`
- `provider`
- `api_style`
- `modalities`
- `supports_image_input`
- `supports_tool_calling`
- `supports_json_mode`
- `rate_limit_profile`

## 15.4 BenchmarkSpec

**职责**：描述 Benchmark 的任务、环境和评分能力。  
**关键属性**：
- `benchmark_id`
- `integration_mode`
- `task_source`
- `metric_schema`
- `device_backend`
- `reset_requirements`
- `required_env`

## 15.5 TrialSpec

**职责**：定义一个最小执行单元。  
**关键属性**：
- `trial_id`
- `run_id`
- `task_id`
- `agent_variant_id`
- `model_binding`
- `seed`
- `runtime_recipe`
- `timeout_sec`
- `max_steps`

## 15.6 RuntimeRecipe

**职责**：描述一个 Trial 的运行配方。  
**关键属性**：
- `agent_runtime`
- `benchmark_runtime`
- `worker_mode`
- `device_profile`
- `reset_strategy`
- `observation_mode`
- `control_backend`
- `env_vars`
- `mounts`

## 15.7 RunContext

**职责**：承载 run 级上下文。  
**关键属性**：
- `run_id`
- `project_snapshot`
- `artifact_root`
- `event_bus`
- `registry`
- `scheduler_state`

## 15.8 TrialContext

**职责**：承载 trial 级运行上下文。  
**关键属性**：
- `trial_spec`
- `emulator_instance`
- `runtime_bridge`
- `artifact_writer`
- `logger`
- `score_state`

## 15.9 EmulatorPoolManager

**职责**：管理模拟器池。  
**关键方法**：
- `provision_pool()`
- `start_instance()`
- `restore_snapshot()`
- `assign_trial()`
- `release_instance()`
- `health_check()`
- `restart_instance()`
- `shutdown_all()`

## 15.10 EmulatorInstance

**职责**：描述一个具体模拟器实例。  
**关键属性**：
- `instance_id`
- `adb_serial`
- `avd_name`
- `grpc_port`
- `appium_port`
- `status`
- `current_trial_id`
- `last_heartbeat_at`

## 15.11 Scheduler

**职责**：调度 Trial 与资源。  
**关键方法**：
- `submit_trials()`
- `next_trial()`
- `mark_running()`
- `mark_completed()`
- `mark_failed()`
- `enqueue_retry()`

## 15.12 TrialOrchestrator

**职责**：编排 Trial 的完整生命周期。  
**关键方法**：
- `run_trial()`
- `prepare_device()`
- `prepare_runtime()`
- `execute_main_loop()`
- `finalize_trial()`

## 15.13 RetryController

**职责**：根据错误类型和策略决定是否重试。  
**关键属性**：
- `retry_budget`
- `retry_on`
- `backoff_policy`

## 15.14 ObservationBundle

**职责**：存储一步原始 observation。  
**关键属性**：
- `screenshot_path`
- `xml_path`
- `parsed_text`
- `activity`
- `package_name`

## 15.15 ActionRecord

**职责**：存储一步动作链。  
**关键属性**：
- `agent_raw_output`
- `parsed_action`
- `executed_action`
- `execution_result`

## 15.16 ScoreBundle

**职责**：统一承载 trial 分数。  
**关键属性**：
- `native_metrics`
- `primary_metric`
- `platform_metrics`
- `notes`

## 15.17 ArtifactWriter

**职责**：把 run / trial / step 数据写入标准目录结构。  
**关键方法**：
- `write_meta()`
- `write_event()`
- `write_step_observation()`
- `write_step_action()`
- `write_score()`

## 15.18 Registry

**职责**：插件注册与发现。  
**关键方法**：
- `register_agent()`
- `register_benchmark()`
- `register_bridge()`
- `resolve_agent()`
- `resolve_benchmark()`
- `resolve_model()`

---

## 16. 目录结构建议

```text
snowl-mobile/
  AGENTS.md
  README.md
  README-FOR-CODEX.md
  PROJECT-DESIGN.md
  CODEX-IMPLEMENTATION-ROADMAP.md
  INTEGRATION-CONTRACTS.md
  project.example.yml
  pyproject.toml
  src/
    snowl_mobile/
      cli/
      core/
      runtime/
      schedulers/
      devices/
      adapters/
        agents/
        benchmarks/
        bridges/
      models/
      scoring/
      artifacts/
      monitor/
      synth/
      schemas/
      utils/
  plugins/
  references/
    agents/
    benchmarks/
  runs/
  tests/
    unit/
    integration/
    e2e/
  docs/
  scripts/
```

补充约定：

- 真实上游 Agent 仓库默认由用户手动 clone 到 `references/agents/<repo_name>/`
- 真实上游 Benchmark 仓库默认由用户手动 clone 到 `references/benchmarks/<repo_name>/`
- Codex 默认职责是读取、分析、适配这些本地 checkout，不把默认联网 clone 作为平台基本行为

---

## 17. 配置文件建议

推荐以 `project.yml` 作为统一入口。核心段落建议包括：

- `project`
- `models`
- `agents`
- `benchmarks`
- `matrix`
- `runtime`
- `devices`
- `retries`
- `artifacts`
- `monitoring`

示意：

```yaml
project:
  name: autoglm-msb-aw
  run_name: demo_run

models:
  - id: gpt4o
    provider: openai
    api_style: openai_chat
    modalities: [text, image]

agents:
  - id: autoglm
    variant: default
    model_ref: gpt4o

benchmarks:
  - id: mobilesafetybench
  - id: androidworld

matrix:
  expand: agent_x_benchmark

runtime:
  batch_size: 5
  worker_mode: venv

devices:
  avd_profile: api34_base
  reset_strategy: snapshot_then_seed

artifacts:
  level: standard
```

---

## 18. 状态机设计

### 18.1 Trial 状态

建议定义如下状态：

- `PENDING`
- `SCHEDULED`
- `PREPARING`
- `RUNNING`
- `SCORING`
- `COMPLETED`
- `FAILED`
- `RETRY_WAITING`
- `SKIPPED`
- `ABORTED`

### 18.2 Run 状态

- `CREATED`
- `PLANNED`
- `BOOTSTRAPPING`
- `RUNNING`
- `PARTIALLY_FAILED`
- `COMPLETED`
- `ABORTED`

---

## 19. 错误分类与重试策略

### 19.1 错误分类

至少区分：

- `MODEL_API_ERROR`
- `MODEL_OUTPUT_PARSE_ERROR`
- `DEVICE_CONNECTION_ERROR`
- `DEVICE_RESET_ERROR`
- `EMULATOR_CRASH`
- `BENCHMARK_SETUP_ERROR`
- `BENCHMARK_RUNTIME_ERROR`
- `AGENT_RUNTIME_ERROR`
- `TIMEOUT_ERROR`
- `SCORER_ERROR`

### 19.2 重试建议

- 模型瞬时失败：优先重试单步；
- 动作解析失败：允许有限次 re-parse / self-correct；
- ADB 断开：重连后继续；
- 模拟器崩溃：重启并恢复 snapshot，然后整 Trial 重跑；
- scorer 出错：保留轨迹并标记评分失败，不直接丢弃 Trial 数据。

---

## 20. 监控与可视化

v0.x 推荐提供两种视图：

1. **CLI TUI / Rich 面板**
   - Run 总体进度
   - 各 Trial 当前状态
   - 失败计数
   - 当前模拟器占用情况

2. **轻量本地 Web**
   - Trial 列表
   - 实时日志流
   - 评分聚合
   - 每一步截图 / XML / action 预览

---

## 21. 给 Codex 的实现建议

### 21.1 必须先立“硬边界”

Codex 实现前，应先固定以下内容：

- 目录结构；
- ProjectSpec schema；
- Adapter 抽象接口；
- Trial 生命周期；
- Artifact 目录结构；
- 错误码与状态机。

这些属于“架构地基”，不能边写边随意改名。

### 21.2 先平台后集成

Codex 的执行顺序不应从“接 AutoGLM”开始，而应先完成：

1. 核心 package 与 CLI 骨架；
2. 配置解析、注册中心、run/trial 模型；
3. artifact store 与 event bus；
4. emulator pool 抽象；
5. 简单 mock benchmark + mock agent 跑通端到端；
6. 再接真实 Agent / Benchmark。

### 21.3 先 Wrap 再 Native

优先接入能尽快跑起来的组合，再逐步把某些桥接适配器原生化。

---

## 22. 里程碑建议

### Phase 0：仓库骨架与核心契约
输出：
- 基础目录
- schema
- registry
- CLI 骨架
- 状态机
- artifact 基础结构

### Phase 1：模拟器池与最小运行闭环
输出：
- emulator pool
- reset 策略框架
- mock agent/mock benchmark
- 并行 Trial 执行

### Phase 2：Wrap 模式集成首批真实项目
输出：
- AutoGLM adapter
- MobileAgent adapter
- MobileSafetyBench adapter
- AndroidWorld adapter
- 至少一组组合可真实跑通

### Phase 3：实时监控与评分聚合
输出：
- live progress
- summary
- score bundle
- 本地 Web 查看器

### Phase 4：轨迹沉淀增强与动态任务合成
输出：
- full artifacts
- synthesis pipeline
- generated benchmark package

---

## 23. 风险与应对

### 23.1 上游仓库频繁变化
应对：  
采用 references + adapter 契约 + bridge wrapper，避免平台核心直接依赖上游内部实现。

同时固定本地 references 目录约定，由用户手动维护 clone，平台与 Codex 只围绕这些稳定路径做分析和集成。

### 23.2 模拟器稳定性不足
应对：  
设备健康检查、snapshot 恢复、重启、失败分类与 Trial 级重试。

### 23.3 环境冲突严重
应对：  
worker 环境隔离，必要时容器化。

### 23.4 轨迹数据占用过大
应对：  
artifact level、压缩、定期清理、按 step 分文件存储。

### 23.5 评分指标异构
应对：  
保留 native metrics，平台只维护少量统一的 operational metrics。

---

## 24. 结论

snowl-mobile 的正确形态不是某个 benchmark 的壳，而是一个围绕 **Trial 编排、模拟器资源管理、环境隔离、数据沉淀与动态测试任务合成** 构建的平台。  
其首要任务不是“尽快兼容所有仓库”，而是先建立稳定的运行契约，使后续 Agent、Benchmark、Model、Scorer 和 Synthesis 模块能够以低摩擦方式不断接入。

只要以下五个地基设计稳定，本项目就具备长期演进能力：

1. `ProjectSpec / TrialSpec / RuntimeRecipe`
2. `Adapter / Bridge / Registry`
3. `EmulatorPoolManager / Scheduler / RetryController`
4. `ArtifactStore / EventBus / ScoreBundle`
5. `Generated Benchmark Package` 形式的动态任务合成输出

以上五项应作为 Codex 实现时不可轻易漂移的核心骨架。
