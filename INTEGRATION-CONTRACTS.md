# INTEGRATION-CONTRACTS.md

本文档定义 snowl-mobile 对外暴露的主要适配接口契约。  
目标不是限制实现细节，而是保证新 Agent / Benchmark 可以按稳定方式接入。

---

## 1. 总体原则

- 平台核心层不直接依赖某个上游仓库的内部实现细节；
- 新接入应优先通过 Adapter / Bridge 的形式完成；
- 平台必须允许 wrap / native / hybrid 三种 integration mode。
- 适配器注册应通过 Registry 完成，平台核心不直接 new 某个具体 adapter 类。

### 1.1 统一 Adapter 元信息

建议所有 Adapter 暴露统一 metadata，至少包含：

- `adapter_id`
- `kind`
- `integration_mode`
- `supported_modalities`
- `supported_backends`
- `required_env`

Registry 应支持：

- 通过字符串 ID 注册 adapter
- 按类型列出 adapter
- 按 metadata 条件查询 adapter
- 按字符串 ID 实例化 adapter

---

## 2. Agent Adapter 契约

### 2.1 必须声明的信息

每个 AgentAdapter 必须能返回 `AgentSpec`，至少包含：

- `agent_id`
- `display_name`
- `variant`
- `model_ref`（若该 AgentSpec 表示 project-scoped runnable variant）
- `integration_mode`
- `required_modalities`
- `supported_modalities`
- `supported_model_protocols`
- `supports_tool_calling`
- `supports_image_input`
- `supports_json_mode`
- `requires_tool_calling`（可选但推荐，用于 fail-fast compatibility check）
- `requires_json_mode`（可选但推荐，用于 fail-fast compatibility check）
- `required_env`
- `action_schema`
- `prompt_contract_version`
- `worker_mode`

### 2.2 推荐接口

```python
class BaseAgentAdapter(ABC):
    def describe(self) -> AgentSpec: ...
    def build_runtime(self, ctx: TrialContext) -> "AgentRuntime": ...
    def metadata(self) -> AdapterMetadata: ...
```

运行时对象建议至少支持：

```python
class AgentRuntime(Protocol):
    def create_session(self) -> None: ...
    def step(self, observation: ObservationBundle) -> AgentStepOutput: ...
    def close_session(self) -> None: ...
```

### 2.3 Wrap 模式快捷接口

若某个 Agent 当前无法方便拆解成逐步 step，可支持：

```python
class WrappedAgentAdapter(BaseAgentAdapter):
    def run_trial(self, ctx: TrialContext) -> TrialExecutionOutput: ...
```

说明：
- `AgentSpec` 在平台中承担“能力描述 + project-scoped variant 声明”双重角色，因此允许带 `model_ref` 与 `variant`；
- 平台应在计划阶段基于 `supported_model_protocols`、modalities、`requires_tool_calling`、`requires_json_mode` 等字段做兼容性检查。

### 2.4 推荐实现结构与责任边界

推荐把 agent adapter 明确拆成以下责任段：

1. `describe()`：声明稳定的 `AgentSpec` 与能力边界；
2. `transform_observation()`：upstream observation -> `ObservationBundle`；
3. `build_runtime()` / wrap runner：主 step/run entry；
4. `normalize_action()`：raw output -> platform action schema；
5. `capture_raw_output()`：保留原始模型输出、tool trace、确认记录等；
6. `metadata()`：导出 registry 所需元信息。

说明：

- observation transform 不应被隐式塞进 prompt 拼装逻辑；
- action normalization 不应和平台 action execution 混写；
- raw output capture 不应被归一化动作覆盖；
- 设备控制入口、模型调用入口、人工确认入口都应在 adapter contract 或 scaffold 中显式标注，便于后续隔离运行与审计。

### 2.5 AgentSpec 与 ModelSpec 兼容性声明

推荐把“agent 能力声明”和“model 兼容性约束”拆清楚：

- `supported_modalities` / `required_modalities`：agent 对模型输入模态的要求；
- `supported_model_protocols`：agent 兼容的模型协议集合；
- `supports_image_input` / `supports_tool_calling` / `supports_json_mode`：agent 自身实现侧能力；
- `requires_tool_calling` / `requires_json_mode`：agent 对模型能力的硬要求；
- `model_ref`：project-scoped 绑定，不等于通用能力声明。

建议校验语义：

- model `api_style` 必须落在 `supported_model_protocols` 内；
- model `modalities` 必须覆盖 agent `required_modalities`；
- 若 agent 需要图像输入，则 model 也必须支持图像输入；
- 若 agent `requires_tool_calling=true`，则 model 必须 `supports_tool_calling=true`；
- 若 agent `requires_json_mode=true`，则 model 必须 `supports_json_mode=true`。

---

## 3. Benchmark Adapter 契约

### 3.1 必须声明的信息

每个 BenchmarkAdapter 必须能返回 `BenchmarkSpec`，至少包含：

- `benchmark_id`
- `display_name`
- `integration_mode`
- `task_source`
- `metric_schema`
- `scorer_ref`
- `reset_policy`
- `reset_requirements`
- `device_backend`
- `required_env`
- `supported_agent_ids`（可选但推荐）

其中建议语义如下：
- `task_source`：任务来源描述，如 `reference_repo`、`local_path`、`generated_package`；
- `scorer_ref`：benchmark 原生 scorer 的稳定引用名；
- `reset_policy`：该 benchmark 期望的平台 reset policy 名称；
- `supported_agent_ids`：若 benchmark 只支持部分 agent，可在计划阶段直接 fail-fast。

### 3.2 推荐接口

```python
class BaseBenchmarkAdapter(ABC):
    def describe(self) -> BenchmarkSpec: ...
    def list_tasks(self, project_ctx: RunContext) -> list[TaskSpec]: ...
    def prepare_trial(self, ctx: TrialContext) -> None: ...
    def seed_environment(self, ctx: TrialContext) -> None: ...
    def get_initial_observation(self, ctx: TrialContext) -> ObservationBundle: ...
    def apply_action(self, ctx: TrialContext, action: ParsedAction) -> StepResult: ...
    def is_terminated(self, ctx: TrialContext) -> bool: ...
    def score_trial(self, ctx: TrialContext) -> ScoreBundle: ...
    def cleanup_trial(self, ctx: TrialContext) -> None: ...
    def metadata(self) -> AdapterMetadata: ...
```

### 3.3 推荐实现结构与责任边界

推荐把 benchmark adapter 明确拆成以下责任段：

1. `list_tasks()`：task discovery
2. `prepare_trial()`：pre-task setup
3. `seed_environment()`：benchmark-native environment init / reset
4. `get_initial_observation()` 或 wrap runner 前置转换：observation form -> `ObservationBundle`
5. `run_entry` / wrap runner：主执行入口
6. `score_trial()` / native scorer hook：score capture
7. `cleanup_trial()`：cleanup
8. `capture_raw_artifacts()`：截图 / XML / log / trace 等原始产物点位

说明：

- 平台级 reset 与 benchmark-native reset 必须分开建模；
- benchmark native metrics 不应被 platform metrics 覆盖；
- raw artifact capture 点位要在 adapter 侧显式记录，便于后续 artifact store 和调试。

### 3.4 Benchmark native metrics 与 platform metrics 映射

建议遵循：

- `ScoreBundle.native_metrics`：保留 benchmark-native 的原始指标；
- `ScoreBundle.primary_metric`：选一项对平台汇总最重要的指标；
- `ScoreBundle.platform_metrics`：补充 run/trial/worker/device/retry 等平台侧指标；
- 若 benchmark native metric 与 platform metric 有映射关系，应在 adapter 或 scaffold contract 中显式声明，而不是隐式重命名。

---

## 4. Bridge Adapter 契约

Bridge Adapter 用于处理某个 Agent 与某个 Benchmark 的特殊耦合组合。

### 4.1 使用场景

- 上游仓库中 agent 与 benchmark 共用 prompt/action parser；
- 单独拆分成本过高；
- 首期目标是优先跑通真实 case。

### 4.2 命名建议

`<agent_id>__<benchmark_id>`

例如：
- `autoglm__mobilesafetybench`
- `mobileagent__androidworld`

### 4.3 返回信息

Bridge Adapter 仍然要能映射回标准 TrialResult / ScoreBundle / Artifact refs。

推荐基础形式：

```python
class BaseBridgeAdapter(ABC):
    @property
    def agent_id(self) -> str: ...
    @property
    def benchmark_id(self) -> str: ...
    def describe_bridge(self) -> BridgeContract: ...
    def metadata(self) -> AdapterMetadata: ...
    def run_trial(self, ctx: TrialContext) -> TrialExecutionOutput: ...
```

### 4.4 推荐职责边界

推荐把 bridge 限定在 pair-specific glue，而不是重新实现整套 agent 或 benchmark：

1. `map_observation()`：组合级 observation remapping
2. `map_action()`：组合级 action remapping
3. `run_entry` / `run_trial()`：组合级执行入口
4. `environment_handshake()`：组合级端口、env、sidecar、launch hint 协调
5. `capture_bridge_artifacts()`：组合级原始产物点位

说明：

- 如果问题属于 agent 单边能力，不应先引入 bridge；
- 如果问题属于 benchmark 单边协议，也不应先引入 bridge；
- 只有“agent 和 benchmark 都没错，但组合还是不通”时，bridge 才是一等扩展点。

### 4.5 Pair-Specific Runtime Recipe 契约

平台允许在项目配置里声明 pair-specific runtime recipe，用于给某个固定组合覆写默认 runtime shell。

建议字段至少包含：

- `recipe_id`
- `agent_id`
- `benchmark_id`
- `bridge_id`
- `requires_bridge`
- `worker_mode`
- `env_isolation`
- `device_profile`
- `control_backend`
- `reset_policy`
- `backend_requirements`
- `required_env`
- `env_vars`
- `mounts`
- `ports`
- `launch_hints`

建议语义：

- `bridge_id`：声明这条 recipe 对应的 bridge；
- `requires_bridge`：若为 true，则 plan 阶段必须能解析到 bridge；
- `ports`：保留 pair-only 端口需求；
- `launch_hints`：保留 sidecar、handshake、entrypoint 等组合级提示；
- `worker_mode` / `env_isolation`：允许组合级覆写，但仍应通过 compatibility 检查。

---

## 5. Model Provider 契约

平台中的模型不是裸字符串，而应描述为 `ModelSpec`。  
建议至少包含：

- `model_id`
- `provider`
- `api_style`
- `modalities`
- `supports_image_input`
- `supports_tool_calling`
- `supports_json_mode`
- `rate_limit_profile`

平台建议在 `ProjectSpec.validate()` 中至少检查：
- Agent 的 `model_ref` 是否存在；
- `supported_model_protocols` 与 `api_style` 是否匹配；
- `required_modalities` 是否为 model `modalities` 的子集；
- `requires_tool_calling` / `requires_json_mode` 是否满足。

Provider 运行时建议支持：

```python
class ModelClient(Protocol):
    def invoke(self, request: ModelRequest) -> ModelResponse: ...
```

---

## 6. Observation / Action 契约

### 6.1 ObservationBundle

原始 Observation 必须独立保存，不应被 prompt 文本覆盖。

建议字段：

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

### 6.2 ActionRecord

建议字段：

- `agent_raw_output`
- `parsed_action`
- `executed_action`
- `execution_result`

---

## 7. Artifact 契约

每个 Trial 至少落盘：

- `meta.json`
- `runtime_recipe.json`
- `score.json`
- `trajectory.json`

若 artifact level ≥ standard，再保存：

- step screenshots
- step xml
- obs/action json refs
- stdout/stderr logs

项目级建议显式声明 `ArtifactPolicy`，至少包含：
- `level`
- `root_dir`
- `persist_step_artifacts`
- `persist_logs`
- `persist_prompt_payloads`

### 7.1 当前 run / trial 目录规范

当前仓库已经固定的最小 run layout 为：

```text
runs/<run_id>/
  manifest.json
  plan.json
  summary.json
  events.jsonl
  run.log
  project.snapshot.yml
  trials/
    <trial_id>/
      meta.json
      runtime_recipe.json
      score.json
      trajectory.json
      trial.log
      steps/
```

其中：

- `manifest.json`：run 级元数据、layout version、artifact level、关键文件索引；
- `plan.json`：计划展开结果与兼容性诊断；
- `summary.json`：run 级计数器、最终状态、trial 摘要；
- `events.jsonl`：run/trial 生命周期事件流；
- `run.log`：run 级文件日志；
- `trial.log`：trial scoped 文件日志。

### 7.2 Trajectory step 持久化字段

`trajectory.json` 中的每个 step 当前建议至少包含：

- `step_index`
- `attempt`
- `status`
- `observation`
- `action`
- `artifacts`
- `timestamps`

其中：

- `observation` 保存 observation metadata，如 `parsed_text`、`activity`、`package_name`、`source_backend`；
- `artifacts.screenshot_path` / `artifacts.xml_path` 保存 step 级截图和 XML 路径；
- `artifacts.observation_path` / `artifacts.action_path` 保存 step 级 JSON payload 路径；
- `timestamps` 至少包含 `observed_at`、`action_at`、`persisted_at`。

### 7.3 Artifact level 语义

- `light`：保留 run/trial 元数据和 `trajectory.json`，不强制生成 step 文件；
- `standard`：生成 step observation/action JSON 与截图/XML 占位文件；
- `full`：在 `standard` 基础上允许额外保存 prompt/model IO 等扩展 payload。

---

## 8. 注册机制

所有 Adapter 都应通过 Registry 注册，而不是在核心逻辑里硬编码 if-else。

建议注册表提供：

---

## 9. Worker 隔离契约

平台当前已经固定一个最小 host/worker 边界，用来避免未来 Agent / Benchmark 依赖互相污染。

### 9.1 核心对象

- `WorkerSpec`：host 根据 `RuntimeRecipe` 派生出来的 worker 启动描述；
- `WorkerTransport`：当前提供 `in_process` 与 `subprocess + JSON lines / stdio` 两种传输形态；
- `WorkerResult`：worker 返回给 host 的结构化 trial 结果；
- `WorkerLauncher`：负责 `RuntimeRecipe -> WorkerSpec -> Transport` 的映射与错误归一化。

### 9.2 RuntimeRecipe 到 worker 的当前映射

- `worker_mode = in_process` -> `execution_mode = in_process`
- `worker_mode = venv` -> `execution_mode = subprocess`
- `worker_mode = container` -> `execution_mode = subprocess`

说明：
- 当前阶段先稳定 host/worker 协议，不在这里实现完整 `venv/conda/container` 环境管理；
- `requested_mode` 仍然会原样保留在 `WorkerSpec` / `WorkerResult` 中，方便后续引入更具体的 launcher backend。

### 9.3 最小 worker 协议

当前 subprocess worker 通过 stdio 交换 JSON lines：

1. `initialize`
2. `run_trial`
3. `shutdown`

worker 返回：

- `initialized`
- `trial_result`

并要求：

- stdout 只输出协议 JSON；
- 非协议日志写到 stderr；
- malformed JSON、提前退出、超时都必须在 host 侧转成标准 worker 错误类型。

### 9.4 当前 worker 错误归一化

当前 host 会把 worker 级异常统一成：

- `WORKER_TRANSIENT_ERROR`
- `WORKER_TIMEOUT`
- `WORKER_CRASH`
- `WORKER_PROTOCOL_ERROR`

其中 retryable 与否由 `WorkerResult.retryable` 显式返回，再交给 `RetryController` 处理。

- `register_agent`
- `register_benchmark`
- `register_bridge`
- `register_scorer`
- `register_model_provider`
- `register_reset_strategy`
- `instantiate_agent`
- `instantiate_benchmark`
- `query(kind=..., integration_mode=..., modality=..., backend=...)`

## 8.1 Compatibility Resolver

建议提供独立的 `CompatibilityResolver`，至少支持：

- `AgentSpec × ModelSpec`
- `AgentSpec × BenchmarkSpec`
- `BenchmarkSpec × RuntimeRecipe`

输出应为可读诊断，而不是单个布尔值，便于 dry-run 和计划阶段 fail-fast。

---

## 9. 新集成的最低验收要求

任意新 Agent 或 Benchmark 接入时，至少需要满足：

1. 能被 Registry 发现；
2. 能返回合法 Spec；
3. 至少有一个最小 demo 配置；
4. 运行失败时能产生标准错误类型；
5. 能输出标准 Trial artifact。

---

## 10. Emulator 资源契约

当前平台已经把 emulator 当成显式调度资源，而不是隐式外部依赖。

### 10.1 核心对象

- `EmulatorInstance`：描述一个具体 slot，至少包含 `instance_id`、`adb_serial`、`appium_port`、`grpc_port`、`avd_name`、`snapshot_name`、`status`、`current_trial_id`、`last_heartbeat_at`；
- `EmulatorLease`：描述某个 trial 对一个 emulator slot 的独占占用；
- `HealthStatus`：当前至少区分 `UNKNOWN / HEALTHY / DEGRADED / UNHEALTHY`；
- `EmulatorPoolManager`：负责 provision、health check、assign、release、restart、shutdown；
- `ResetManager`：负责把 benchmark/project reset policy 归一化成平台级 reset 执行动作。

### 10.2 当前 reset 策略框架

当前最小 reset 策略支持：

- `none`
- `restore_snapshot`
- `benchmark_native_reset`
- `restore_snapshot_then_seed`

其中：

- `restore_snapshot_then_seed` 允许先做平台级 snapshot restore，再记录 benchmark seeding 请求；
- benchmark-specific seed 细节在当前阶段仍然只保留接口和记录，不真正执行。

### 10.3 Scheduler 与 emulator 的关系

当前调度器支持按 emulator slot 取任务：

- 若有兼容 profile 的空闲实例，则返回 `TrialState + EmulatorLease`；
- 若实例都忙或不健康，则 trial 继续留在队列里；
- trial 完成后由 orchestrator/demo 显式 release lease。

这保证了以后接入真实模拟器时，Trial 与设备实例的关系仍然是显式、可追踪、可落盘的。
