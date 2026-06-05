# 贡献指南

感谢你关注 RepoPilot。这个项目的目标是把“进入陌生代码仓库前的侦察工作”做成一个边界清晰、只读优先、可复用、可审计、可维护的 Agent。

## 开发环境

RepoPilot 需要 Python 3.12 或更高版本。

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[dev]"
python -m pytest tests
python -m build
```

运行时配置、API Key 和报告默认保存在 RepoPilot home。可以通过 `REPOPILOT_HOME` 指定自定义目录；不要把运行时目录、私有报告或 API Key 提交到仓库。

## 分支策略

- `main` 是稳定分支，应始终保持 CI 通过，并尽量处于可发布状态。
- 仓库规则要求对 `main` 的改动通过 Pull Request 合并；不要直接向 `main` 推送功能或修复提交。
- 非平凡改动应先创建 issue，再从最新 `main` 创建聚焦分支开发。
- 拼写、链接、注释、轻量文档修正等 trivial change 可以不单独创建 issue，但仍应通过 PR 合并，并在 PR 中说明范围。
- 推荐分支命名：
  - `fix/<short-topic>`：缺陷修复。
  - `feat/<short-topic>`：新能力。
  - `docs/<short-topic>`：文档和流程。
  - `test/<short-topic>`：测试覆盖。
  - `refactor/<short-topic>`：不改变行为的结构调整。

## Issue 策略

除 trivial change 外，建议先创建 issue。一个好的 issue 应说明：

- 当前问题或目标用户流程。
- 期望行为。
- 影响范围，包括 CLI、MCP 工具、配置、文档、测试和安全边界。
- 验收标准。
- 是否存在迁移或兼容性影响。

PR 应使用 `Closes #<issue-number>` 或 `Fixes #<issue-number>` 关联对应 issue。没有对应 issue 的 trivial change 应在 PR 中说明原因。

## Pull Request 策略

PR 应保持聚焦，避免把无关重构、格式化和功能改动混在一起。提交 PR 前请确认：

- 已关联 issue，或说明这是 trivial change。
- `python -m pytest tests` 通过，或说明未运行原因。
- `python -m build` 通过，或说明未运行原因。
- `git diff --check` 通过。
- 文档、CLI 帮助、配置参考和测试已随行为变化同步更新。
- 没有提交 RepoPilot home、`.env`、API Key、私有仓库报告或本机绝对路径。
- 没有把被分析仓库中的私有代码复制进 issue、PR 或测试样例。

涉及 CLI 输出、终端 UI 或 WebUI 的改动，请附上简短截图或文字示例。

## Release 策略

- 版本号遵循 SemVer 风格：`MAJOR.MINOR.PATCH`。
- `0.1.x` 阶段允许较小破坏性调整，但必须在 README、CHANGELOG 或迁移说明中写清楚。
- tag 视为不可变发布点。除非出现严重发布事故，已推送 tag 不应撤销或重打。
- 发布前应确认 `main` 上 CI 通过、`python -m build` 通过、工作区干净、CHANGELOG 已更新。
- Release notes 应按 issue/PR 整理用户可理解的变化，而不是简单复制 commit 列表。

## 修改 MCP 工具

新增或修改工具时，请同步检查：

- `src/repopilot/tools/`
- `src/repopilot/mcp_server.py`
- `src/repopilot/settings_store.py` 中各模式的 `enabled_tools`
- CLI 中的 `/mcp`、`/tools` 展示
- README 和 `docs/configuration.md`
- 相关测试

工具默认应保持只读，写入能力只允许写到 RepoPilot 自己的运行时目录或报告目录。

## 修改配置项

新增配置项时，请同步检查：

- `src/repopilot/config.py`
- `src/repopilot/settings_store.py`
- `docs/configuration.md`
- CLI 的 `/settings` 和 `repopilot config` 行为
- 测试中的最小配置样例

配置项应尽量有明确默认值，并避免要求用户手动编辑文件才能完成常见操作。涉及 API Key、路径授权、联网能力或写入目录的改动，应额外说明安全影响。