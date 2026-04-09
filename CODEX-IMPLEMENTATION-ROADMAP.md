# CODEX-IMPLEMENTATION-ROADMAP.md

本文档定义 snowl-mobile 的建议实施顺序、阶段目标、验收标准与交付物。

---

## Phase 0：仓库骨架与核心契约

### 目标
建立不会轻易推翻的基础骨架。

### 必做项
- 初始化 Python 项目与 `src/` 布局
- 建立基础 CLI 入口
- 定义核心 schema / dataclass / pydantic model
- 建立 Registry
- 建立 ArtifactStore / EventBus 最小实现
- 建立 Trial / Run 状态枚举
- 提供最小 README 与示例配置

### 关键输出
- `src/snowl_mobile/...`
- `project.example.yml`
- 基础测试
- 可以执行的空跑命令

### 验收标准
- `python -m snowl_mobile --help` 可运行
- 能加载并校验示例 project.yml
- 能创建 run 目录并写入 manifest / events / summary 占位文件
- 核心模型命名与职责与设计文档一致

---

## Phase 1：模拟器池与最小 Trial 闭环

### 目标
在不接真实上游项目的情况下，跑通 “配置 -> Trial -> artifact -> summary” 最小闭环。

### 必做项
- 实现 EmulatorPoolManager 抽象
- 实现 DeviceProfile / ResetStrategy 抽象
- 实现 Scheduler 与 RetryController 最小版本
- 实现 MockAgentAdapter
- 实现 MockBenchmarkAdapter
- 实现 TrialOrchestrator

### 关键输出
- 模拟器抽象层
- mock benchmark / mock agent
- 一次多 Trial 并发 demo

### 验收标准
- 可配置 batch_size > 1
- Scheduler 能动态分配下一个 Trial 给空闲 slot
- 每个 Trial 产生独立目录
- 失败 Trial 能进入 retry 队列
- summary 中能统计 completed / failed / retry counts

---

## Phase 2：Worker 环境隔离与 RuntimeBridge

### 目标
为真实 Agent / Benchmark 接入建立运行时隔离基础。

### 必做项
- 定义 worker mode 枚举
- 定义 RuntimeBridge 协议
- 实现 in_process bridge
- 实现 venv worker bridge 骨架
- 定义外部命令、环境变量、路径配置集中管理方式

### 验收标准
- 平台可用统一接口调用 in_process adapter
- 平台可启动一个最小的 venv worker 并通信
- worker 异常可被 host 捕获并转成标准错误类型

---

## Phase 3：Wrap 模式接入首批真实 Benchmark / Agent

### 目标
优先实现“能运行”。

### 首批目标
- AutoGLM
- MobileAgent
- MobileSafetyBench
- AndroidWorld

### 建议策略
- 先做 wrap adapter / bridge adapter
- 必要时为具体 pair 设计 bridge
- 不强求第一阶段就把所有组件完全拆为纯原生接口

### 验收标准
- 至少 1 组真实组合可从平台入口跑通
- 跑完后有统一的 score.json / trajectory.json / logs
- 至少能处理模型失败、设备失败、超时中的一种恢复

---

## Phase 4：实时监控、指标聚合与可视化

### 目标
让平台在长时间批量运行时可观测。

### 必做项
- CLI 进度面板
- run/trial 状态查询
- primary metric 聚合
- fail reason 聚合
- 本地轻量 Web viewer（可选但推荐）

### 验收标准
- 用户可以实时看到每组 Agent × Benchmark 的完成进度
- 用户可以快速定位失败 Trial 与日志文件

---

## Phase 5：原生化与适配器清理

### 目标
逐步减少桥接与黑盒封装，提升通用性。

### 必做项
- 提炼通用 AgentAdapter/BenchmarkAdapter 接口
- 将首批最常用路径从 wrap/hybrid 迁移为 native
- 统一 observation/action contract

### 验收标准
- 至少一个 BenchmarkAdapter 与一个 AgentAdapter 为平台原生实现
- bridge adapter 数量不再增长失控

---

## Phase 6：动态安全任务合成

### 目标
让平台从“运行现有 benchmark”扩展到“生成 benchmark”。

### 必做项
- rule parser
- scenario synthesizer
- task materializer
- environment seed builder
- generated benchmark package 格式
- 与主引擎衔接

### 验收标准
- 给定规则文档，能够输出一个可被主引擎运行的 generated benchmark
- 生成任务具备基础元数据、seed 和 scorer 映射

---

## 通用验收规则

每个 Phase 完成后必须满足：

1. 有明确代码边界；
2. 有最小测试或 demo 命令；
3. 有文档同步更新；
4. 不引入大面积临时命名和重复逻辑；
5. 不破坏已有 Phase 的稳定行为。
