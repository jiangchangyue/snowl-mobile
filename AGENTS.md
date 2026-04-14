# AGENTS.md

本仓库用于从 0 开发 **snowl-mobile**：一个面向 Mobile Agent 动态安全评测的平台化框架。

## 你在本仓库中的角色

你不是在做一次性 demo，也不是在拼装几个 shell 脚本。  
你需要实现一个长期可维护的系统，其核心目标是：

- 统一编排 Mobile Agent × Benchmark × Model × Emulator 的运行；
- 支持多模拟器并发 batch 评测；
- 支持失败重试、设备恢复、环境隔离；
- 支持完整轨迹和评分产物沉淀；
- 支持新 Agent / Benchmark 的低摩擦接入；
- 后续支持动态安全测试任务合成。

## 必须遵守的全局原则

1. **先搭平台骨架，再接入真实仓库。**  
   不要一上来就写 AutoGLM 或 AndroidWorld 的耦合代码。

2. **不要破坏核心契约。**  
   下列对象一旦落地，除非明确说明，不得随意推翻命名与职责：
   - ProjectSpec
   - TrialSpec
   - RuntimeRecipe
   - AgentSpec
   - BenchmarkSpec
   - ScoreBundle
   - ObservationBundle
   - ArtifactStore / EventBus
   - EmulatorPoolManager
   - Scheduler
   - RetryController

3. **先 Wrap，后 Native。**  
   初期允许通过 subprocess / RPC 包装上游仓库；后续再渐进式原生化。

4. **环境隔离优先。**  
   不要试图把所有上游 requirements 合并到同一个 Python 环境。

5. **模拟器是一等资源。**  
   调度器必须显式感知 emulator slot，而不是把设备当作外部隐式依赖。

6. **轨迹即资产。**  
   每个 Trial 的 screenshots、xml、trajectory、score、log 必须能稳定落盘。

## 先读这些文件，再改代码

实现前必须优先阅读并遵循以下文档：

1. `PROJECT-DESIGN.md`
2. `README-FOR-CODEX.md`
3. `CODEX-IMPLEMENTATION-ROADMAP.md`
4. `INTEGRATION-CONTRACTS.md`
5. `REPOSITORY-BOOTSTRAP.md`

## 实现风格要求

- 代码以可维护性优先，避免临时 patch 风格的拼接；
- 明确分层，不要把 CLI、调度、设备控制、适配器、评分逻辑混写；
- 每个阶段都要补最小可运行测试；
- 每新增一个重要模块，都要补类型定义、异常类型和日志点；
- 所有路径、环境变量、外部命令都要集中封装，避免散落。

## 每个阶段的输出要求

每完成一个阶段，必须同时给出：

1. 本阶段新增/修改的文件清单；
2. 当前架构是否与设计说明书一致；
3. 可运行验证命令；
4. 已知限制；
5. 下一阶段建议。

## 禁止事项

- 不要把核心状态放在全局变量里；
- 不要在没有 schema 的情况下到处传裸 dict；
- 不要把 Trial 结果只打印到终端而不落盘；
- 不要直接耦合某个上游仓库的内部目录结构到平台核心层；
- 不要为了跑通单个 case 而牺牲通用架构。

## 当前优先级

以 `CODEX-IMPLEMENTATION-ROADMAP.md` 中的 Phase 顺序执行。  
默认目标是：先把平台最小闭环做出来，再逐步接入真实 Agent 和 Benchmark。
