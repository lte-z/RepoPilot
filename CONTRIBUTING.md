# 贡献指南

感谢你关注 RepoPilot。这个项目的目标是把“进入陌生代码仓库前的侦察工作”做成一个边界清晰、只读优先、可复用的 Agent。

## 开发环境

RepoPilot 需要 Python 3.12 或更高版本。

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[dev]"
python -m pytest tests
```

运行时配置、API Key 和报告会保存在 `.repopilot/`，该目录已被 Git 忽略。

## 提交前检查

提交前请至少确认：

- `python -m pytest tests` 通过。
- `git diff --check` 通过。
- 没有提交 `.repopilot/`、`.env`、API Key、私有仓库报告或本机绝对路径。
- 没有把被分析仓库中的私有代码复制进 issue、PR 或测试样例。

## 修改 MCP 工具

新增或修改工具时，请同步检查：

- `src/repopilot/tools/`
- `src/repopilot/mcp_server.py`
- `src/repopilot/settings_store.py` 中各模式的 `enabled_tools`
- CLI 中的 `/mcp`、`/tools` 展示
- README 和 `docs/configuration.md`
- 相关测试

工具默认应保持只读，写入能力只允许写到配置的报告目录。

## 修改配置项

新增配置项时，请同步检查：

- `src/repopilot/config.py`
- `src/repopilot/settings_store.py`
- `docs/configuration.md`
- CLI 的 `/settings` 和 `repopilot config` 行为
- 测试中的最小配置样例

配置项应尽量有明确默认值，并避免要求用户手动编辑文件才能完成常见操作。

## Pull Request

PR 请保持聚焦，说明改动目的、运行过的测试以及可能影响的命令或配置项。涉及 CLI 输出的改动，请附上简短截图或文字示例。
