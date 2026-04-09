# Integration Readiness Checklist

本文档给最终用户和 Codex 使用，用于确认“是否已经准备好接入第一个真实仓库”。

## 1. clone 前需要检查什么

- 你已经决定要接的是 `Agent` 还是 `Benchmark`
- 你知道目标仓库会被放到哪个固定路径：
  - `references/agents/<repo_name>/`
  - `references/benchmarks/<repo_name>/`
- 你接受默认工作流是“用户手动 clone，本地分析，本地适配”，而不是默认联网 clone
- 你已经能在本仓库里跑通基础命令：
  - `PYTHONPATH=src python3 -m snowl_mobile validate-config project.example.yml`
  - `PYTHONPATH=src python3 -m snowl_mobile plan project.example.yml`
  - `PYTHONPATH=src python3 scripts/devtools.py test`

## 2. clone 后需要做什么

- 把真实仓库放到固定 references 路径
- 确认至少能看到这些文件中的一部分：
  - `README*`
  - `requirements*.txt`
  - `pyproject.toml` / `setup.py` / `setup.cfg`
  - 主包目录
  - `examples/`
- 先阅读本仓库文档：
  - `README.md`
  - `docs/integrate-agent.md`
  - `docs/integrate-benchmark.md`
  - `docs/integrate-pair.md`
  - `docs/prompts/integrate-agent-prompt.md`
  - `docs/prompts/integrate-benchmark-prompt.md`
- 然后把对应 Prompt 发给 Codex，而不是直接自己猜测 glue code 结构

## 3. Codex 接入完成后需要验证什么

- 新的 adapter / config / tests / docs 已经落盘
- 新增内容的路径、模块名、命令面和当前平台一致
- 下面命令必须能跑：
  - `PYTHONPATH=src python3 scripts/devtools.py lint`
  - `PYTHONPATH=src python3 scripts/devtools.py test`
  - `PYTHONPATH=src python3 -m snowl_mobile validate-config <new_config>.yml`
  - `PYTHONPATH=src python3 -m snowl_mobile plan <new_config>.yml`
  - `PYTHONPATH=src python3 -m snowl_mobile dry-run <new_config>.yml --output-dir /tmp/<run_dir>`
- 如果出现组合级问题，要继续确认：
  - 是否需要 `BaseBridgeAdapter`
  - 是否需要 `pair_runtime_recipes`
  - `plan` 输出里是否出现 `bridge_id / pair_recipe_id`

## 4. 最小成功标准

- 用户已经能手动 clone 第一个真实仓库到 `references/`
- 对应 Prompt 已发给 Codex
- Codex 已经生成接入代码和最小验证
- 用户已完成 `validate-config / plan / dry-run / smoke integration`
