# 集成 Benchmark 的专用 Prompt

把下面这段 Prompt 中的占位符替换后，可以直接发给 Codex。  
前提假设：真实 benchmark 仓库已经由用户手动 clone 到 `references/benchmarks/<repo_name>/`。

需要替换的占位符：

- `<repo_name>`
- `<adapter_id>`
- `<package_name>`
- `<config_name>`

可直接复制的 Prompt：

```text
你现在位于 snowl-mobile 仓库根目录。请只做“接入一个新的 Benchmark 仓库”相关工作，不要接入任何其他真实仓库。

真实 benchmark 仓库已经由用户手动 clone 到：
- references/benchmarks/<repo_name>/

开始前必须先完整阅读并遵守这些文档：
1. AGENTS.md
2. README-FOR-CODEX.md
3. CODEX-IMPLEMENTATION-ROADMAP.md
4. INTEGRATION-CONTRACTS.md
5. REPOSITORY-BOOTSTRAP.md
6. README.md
7. docs/integrate-benchmark.md
8. docs/integrate-pair.md
9. project.example.yml

然后按下面步骤执行：

一、先分析第三方仓库
- 必须先分析 references/benchmarks/<repo_name>/ 中的以下内容：
  - README*
  - requirements*.txt
  - pyproject.toml / setup.py / setup.cfg
  - 主包目录
  - examples/
  - evaluation / scorer / runner 入口
  - task manifest / dataset / scenario 文件
  - reset / setup / seeding 相关文件
  - observation / action / artifact capture 相关文件
- 必须先运行并利用这些工具输出：
  - PYTHONPATH=src python3 -m snowl_mobile inspect-repo benchmark references/benchmarks/<repo_name>
  - PYTHONPATH=src python3 -m snowl_mobile integration-checklist benchmark references/benchmarks/<repo_name> --adapter-id <adapter_id>

二、判断 integration_mode
- 必须显式判断该 benchmark 应采用 wrap / native / hybrid 哪一种：
  - wrap：已有现成 runner / evaluation pipeline / scorer，优先包装
  - native：暴露清晰的 task discovery、step loop、observation、scoring API
  - hybrid：task discovery / scorer 可复用，但环境控制或执行希望由平台接管
- 先 wrap，后 native；如果判断有风险，优先保守选 wrap 或 hybrid

三、生成并实现接入骨架
- 必须先用平台自带脚手架生成起点：
  - PYTHONPATH=src python3 -m snowl_mobile scaffold-benchmark-package references/benchmarks/<repo_name> <adapter_id> --output-dir examples/integration
- 在此基础上完成真正接入，至少包括：
  - benchmark adapter 实现
  - register 入口
  - 与当前平台契约一致的 contract/config/docs/test
  - 一个最小示例配置 examples/configs/<config_name>.yml
- 实现时必须严格遵守当前平台契约与路径约定：
  - BaseBenchmarkAdapter
  - BenchmarkSpec
  - RuntimeRecipe / PairRuntimeRecipe
  - ScoreBundle
  - ArtifactStore
  - Registry
- 如果发现该 benchmark 与某个 agent 组合需要组合级 glue，不要硬塞进通用 adapter；应评估是否需要 BaseBridgeAdapter / pair_runtime_recipes，并参考 docs/integrate-pair.md

四、你需要生成或更新的内容
- benchmark adapter 代码
- 注册代码
- 最小示例配置
- 最小 smoke test / integration test
- 对应 README / 接入文档
- 如果有必要，补 pair-specific bridge scaffold 或 pair runtime recipe 示例

五、验证要求
- 改完后必须运行并通过：
  - PYTHONPATH=src python3 scripts/devtools.py lint
  - PYTHONPATH=src python3 scripts/devtools.py test
  - PYTHONPATH=src python3 -m snowl_mobile validate-config examples/configs/<config_name>.yml
  - PYTHONPATH=src python3 -m snowl_mobile plan examples/configs/<config_name>.yml
  - PYTHONPATH=src python3 -m snowl_mobile dry-run examples/configs/<config_name>.yml --output-dir /tmp/snowl-mobile-<adapter_id>
- 不允许跳过失败测试
- 不允许把 TODO 伪装成已完成
- 如果保留 stub，必须显式说明

六、输出要求
- 给出新增/修改文件列表
- 给出核心设计说明
- 给出运行/测试命令
- 给出结果摘要
- 给出遗留风险
```
