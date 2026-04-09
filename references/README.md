# References Workspace

真实第三方仓库默认应由用户手动 clone 到以下固定目录：

- `references/agents/<repo_name>/`
- `references/benchmarks/<repo_name>/`

Codex 的默认职责是读取这些本地仓库、分析结构、生成适配器模板与检查清单；除非用户明确要求并授权，否则不默认联网 clone 上游仓库。
