# REPOSITORY-BOOTSTRAP.md

本文档定义 snowl-mobile 仓库初始化时建议创建的目录、文件与其用途。  
目标是让 Codex 从第一天开始就在正确的骨架上工作。

---

## 1. 顶层目录建议

```text
snowl-mobile/
  AGENTS.md
  README.md
  README-FOR-CODEX.md
  PROJECT-DESIGN.md
  CODEX-IMPLEMENTATION-ROADMAP.md
  INTEGRATION-CONTRACTS.md
  REPOSITORY-BOOTSTRAP.md
  project.example.yml
  pyproject.toml
  src/
    snowl_mobile/
      __init__.py
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
  tests/
    unit/
    integration/
    e2e/
  references/
    agents/
    benchmarks/
  plugins/
  scripts/
  docs/
  runs/
```

---

## 2. 首批建议创建的文件

### 顶层
- `README.md`
- `AGENTS.md`
- `README-FOR-CODEX.md`
- `PROJECT-DESIGN.md`
- `CODEX-IMPLEMENTATION-ROADMAP.md`
- `INTEGRATION-CONTRACTS.md`
- `REPOSITORY-BOOTSTRAP.md`
- `project.example.yml`
- `pyproject.toml`

### `src/snowl_mobile/`
- `__init__.py`
- `__main__.py`
- `version.py`

### `src/snowl_mobile/cli/`
- `main.py`

### `src/snowl_mobile/core/`
- `project_spec.py`
- `trial_spec.py`
- `runtime_recipe.py`
- `run_context.py`
- `trial_context.py`
- `states.py`
- `errors.py`
- `registry.py`

### `src/snowl_mobile/runtime/`
- `trial_orchestrator.py`
- `runtime_bridge.py`
- `worker_modes.py`

### `src/snowl_mobile/schedulers/`
- `scheduler.py`
- `retry_controller.py`

### `src/snowl_mobile/devices/`
- `emulator_pool.py`
- `emulator_instance.py`
- `reset_strategy.py`
- `device_profile.py`

### `src/snowl_mobile/adapters/agents/`
- `base.py`
- `mock_agent.py`

### `src/snowl_mobile/adapters/benchmarks/`
- `base.py`
- `mock_benchmark.py`

### `src/snowl_mobile/adapters/bridges/`
- `base.py`

### `src/snowl_mobile/models/`
- `model_spec.py`
- `provider_base.py`

### `src/snowl_mobile/scoring/`
- `score_bundle.py`

### `src/snowl_mobile/artifacts/`
- `artifact_writer.py`
- `event_bus.py`
- `paths.py`

### `src/snowl_mobile/schemas/`
- `observation.py`
- `action.py`

---

## 3. 首批测试建议

### `tests/unit/`
- `test_project_spec.py`
- `test_registry.py`
- `test_artifact_writer.py`

### `tests/integration/`
- `test_mock_run_e2e.py`

---

## 4. 首批最小命令目标

建议在 Phase 0 / 1 结束时能够运行：

```bash
python -m snowl_mobile validate project.example.yml
python -m snowl_mobile run project.example.yml
```

至少做到：

- 成功解析配置；
- 生成 run 目录；
- 生成 summary/events/manifest；
- 使用 mock adapter 跑完最小 demo。

---

## 5. references 目录用途

该目录用于放置用户 clone 的上游仓库。  
例如：

```text
references/
  agents/
    Open-AutoGLM/
    MobileAgent/
  benchmarks/
    mobilesafetybench/
    android_world/
```

注意：
- 平台核心代码不得默认直接耦合这些目录的内部结构；
- 具体路径解析应由相应 Adapter / Bridge 层处理；
- 用户未来可替换为本地其他路径，不能写死。

---

## 6. 开发建议

- 所有关键对象优先使用明确 schema；
- 优先建立抽象和测试，再逐步填充具体实现；
- 每个阶段都保持仓库可运行，而不是长期处于“半成品断裂”状态。
