# README-FOR-CODEX.md

## 仓库目标

本项目要实现一个名为 **snowl-mobile** 的平台，用于：

- 在多 Android 模拟器上并发运行 Mobile Agent；
- 将不同 Agent 与不同 Benchmark 进行可配置组合；
- 自动完成任务调度、设备 reset、失败恢复、评分聚合和产物存储；
- 为后续开源生态提供统一接入规范。

## 当前开发策略

本仓库从 0 开发，采用 **分阶段实现**。  
你必须优先完成平台公共骨架，而不是优先优化某个集成细节。

## 系统边界

### 平台负责
- 配置加载与校验
- Trial 计划展开
- 模拟器资源管理
- worker 运行时隔离
- 调度、状态机、重试
- artifacts 与 events 落盘
- 统一运行入口与基础监控

### Agent 负责
- 根据 observation 产出动作
- 自身 prompt / parser / planning 逻辑
- 与特定模型协议的兼容逻辑（通过 AgentSpec 对平台声明）

### Benchmark 负责
- 提供任务集
- 提供 task-specific 环境初始化
- 定义终止条件
- 定义原生评分逻辑

### Model Provider 负责
- 底座模型 API 调用与能力描述

## 核心运行单元

平台的最小运行单元是：

`Trial = BenchmarkTask × AgentVariant × ModelBinding × Seed × RuntimeRecipe`

任何实现都不应退化成“只会跑一个 shell command”的脚本。

## 首批优先落地的对象

- ProjectSpec
- AgentSpec
- BenchmarkSpec
- ModelSpec
- TrialSpec
- RuntimeRecipe
- Registry
- Scheduler
- EmulatorPoolManager
- RetryController
- ArtifactWriter
- EventBus

## 目录约束

请严格遵循 `REPOSITORY-BOOTSTRAP.md` 中建议的目录结构。  
平台核心代码放在：

`src/snowl_mobile/`

其中至少应包含：

- `cli/`
- `core/`
- `runtime/`
- `devices/`
- `schedulers/`
- `artifacts/`
- `adapters/`
- `schemas/`

真实第三方仓库的固定放置目录也已经约定：

- `references/agents/<repo_name>/`
- `references/benchmarks/<repo_name>/`

默认工作流里，这些仓库由用户手动 clone 到本地后再交给 Codex 分析。  
Codex 默认负责读取、检查、生成 scaffold 和适配代码，不负责默认联网 clone。

## 运行模式要求

需要同时为未来保留三种 worker 运行模式：

- `in_process`
- `venv`
- `container`

初期可优先实现 `in_process + venv` 的抽象层与骨架。

## 数据落盘要求

每个 Run 和 Trial 都必须有标准目录。  
禁止只依赖终端输出。  
必须支持：

- run manifest
- plan snapshot
- events.jsonl
- summary.json
- trial meta
- trial score
- trajectory.json
- step-level observation/action refs

## 当前实现优先级

1. schema 和核心 domain model
2. registry 和插件发现
3. artifact store 与 event bus
4. emulator pool 抽象
5. scheduler + retry
6. mock agent / mock benchmark 端到端
7. 再接首批真实集成

## 开发方式

每个阶段结束后都应：

- 能运行至少一个 demo 命令；
- 有测试或最小验证脚本；
- 不留下大面积“以后再重构”的临时代码。

## 第三方接入约束

当用户准备接真实 Agent / Benchmark 时，优先使用以下顺序：

1. 用户手动 clone 到 `references/agents/...` 或 `references/benchmarks/...`
2. Codex 使用本地 checkout 做 repo inspection 和 adapter scaffold
3. Codex 生成 adapter、示例配置、测试与 README 指南
4. 用户运行 `validate-config`、`dry-run`、smoke integration test

除非用户明确要求，否则不要把“自动联网 clone 上游仓库”作为默认步骤。
