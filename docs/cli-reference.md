# CLI 命令参考

本文覆盖 RepoPilot 当前已实现的命令。快速上手可以只运行：

```bash
repopilot
```

不带子命令时，RepoPilot 会进入引导式 CLI：初始化 `.repopilot/`、检查 LLM 配置、选择仓库路径，然后进入多轮会话。

## 输入规则

RepoPilot 的聊天输入分为两类：

- 以 `/` 开头：只按聊天命令解析，不进入自然语言 Agent。
- 不以 `/` 开头：默认先进入 LLM Intent Router；只有 router 判断需要仓库证据时才调用 MCP 工具。

例如 `/help 你还能做什么？` 会被视为错误命令参数；正确写法是 `/help`，或者直接输入 `你还能做什么？`。

## 顶层命令

```bash
repopilot
repopilot setup
repopilot chat <repo_path>
repopilot overview <repo_path>
repopilot runbook <repo_path>
repopilot module-map <repo_path>
repopilot task-brief <repo_path> "<task>"
repopilot deep-scan <repo_path>
repopilot mcp [status|on|off]
repopilot web
```

`repopilot web` 启动实验性本地 WebUI，用于演示一次性分析、工具调用时间线和报告预览；完整多轮会话和配置管理以 CLI 为准。

通用选项：

- `--config <path>`：指定 YAML 配置文件。
- `--offline`：不调用 LLM，只使用本地工具生成摘要。
- `--save`：保存 Markdown 报告到 `.repopilot/reports/`。
- `--json`：对一次性分析命令输出机器可读 JSON。

`repopilot setup --provider <alias>` 可直接使用内置 Provider 预设；当前别名包括 `openai`、`gemini`、`deepseek`、`qwen`、`kimi`、`zhipu`、`openrouter`、`groq`、`siliconflow`。完整 Base URL 和默认模型见 [configuration.md](configuration.md)。

## 聊天命令

| 分类 | 命令 | 说明 |
|---|---|---|
| 起步 | `/help [group]` | 显示命令；分组支持 `chat`、`config`、`mcp`、`reports`。 |
| 起步 | `/status` | 显示会话状态。 |
| 分析 | `/overview` | 生成仓库概览。 |
| 分析 | `/runbook` | 推断安装、运行、测试和构建线索。 |
| 分析 | `/module-map` | 生成模块地图。 |
| 分析 | `/task-brief <task>` | 围绕具体任务生成阅读顺序和风险点。 |
| 分析 | `/deep-scan` | 生成完整仓库入职包。 |
| 工具 | `/mcp [on\|off]` | 显示 MCP 状态或开关 HTTP Fetch 工具。 |
| 工具 | `/tools` | 列出当前会话可用工具。 |
| 证据 | `/sources` | 显示工具证据摘要。 |
| 证据 | `/artifacts` | 列出当前会话报告。 |
| 证据 | `/save [filename.md]` | 保存最近一份报告。 |
| 配置 | `/config` | 显示当前配置摘要。 |
| 配置 | `/settings [get\|set\|reset]` | 查看或修改 YAML 配置。 |
| 配置 | `/provider` | 交互式选择 LLM 供应商、Base URL 和模型。 |
| 配置 | `/api-key` | 交互式保存 API Key。 |
| 会话 | `/setup` | 初始化 `.repopilot/` 本地配置。 |
| 会话 | `/clear` | 清空当前会话上下文并清屏。 |
| 会话 | `/exit` | 退出会话。 |

如果已经保存过 API Key，`/api-key` 和 `repopilot config set-api-key` 会先确认是否覆盖；取消或提交空值都会保留旧值。

## 配置命令

```bash
repopilot config show
repopilot config doctor
repopilot config list
repopilot config schema
repopilot config get <key>
repopilot config set <key> <value>
repopilot config reset <key>
repopilot config add-root <path>
repopilot config remove-root <path>
repopilot config set-provider
repopilot config set-api-key
repopilot config network on
repopilot config network off
```

示例：

```bash
repopilot config get limits.max_tool_rounds
repopilot config set limits.max_tool_rounds 12
repopilot config set limits.llm_timeout_seconds 180
repopilot config set modes.deep-scan.max_tool_rounds 12
repopilot config set modes.task-brief.enabled_tools '["repo_search_text", "repo_read_file", "repo_symbol_map"]'
repopilot config set network.allowed_domains '["docs.python.org", "github.com"]'
repopilot config set ui.animations false
repopilot config set ui.keep_progress_log true
repopilot config set ui.show_user_turns false
repopilot config reset limits.max_tool_rounds
```

`config set` 的值按 YAML 解析，因此 `12` 会成为整数，`true` 会成为布尔值，`["a.com"]` 会成为列表。

Intent Router 相关示例：

```bash
repopilot config get intent.use_llm_router
repopilot config set intent.use_llm_router true
repopilot config set intent.fallback_to_rules true
repopilot config set intent.min_confidence 0.6
```

## MCP 命令

```bash
repopilot mcp
repopilot mcp status
repopilot mcp on
repopilot mcp off
```

`mcp on/off` 当前控制的是联网文本抓取工具 `web_fetch_url`。本地仓库工具始终可用，但仍受权限配置约束。

## 自然语言输入

自然语言输入会先进入 Intent Router：

- “你还能做什么？”：返回能力说明，不调用 MCP。
- “解释一下刚才的结论”：使用会话上下文解释，不重新扫描仓库。
- “分析这个仓库”：进入 overview。
- “怎么运行测试？”：进入 runbook。
- “登录流程在哪里？”：进入 task-brief。
- “给我完整入职包”：进入 deep-scan。

## JSON 输出

一次性分析命令支持 `--json`：

```bash
repopilot overview <repo_path> --json
repopilot deep-scan <repo_path> --json
```

输出包含：

```json
{
  "mode": "overview",
  "repo_path": "...",
  "markdown": "...",
  "offline": false,
  "saved": null,
  "tool_calls": []
}
```

如果意图不清楚，RepoPilot 会提示你换成更明确的问题或使用 slash 命令。

`--offline` 会跳过 LLM Intent Router 和普通聊天 LLM，仅使用本地规则与本地仓库工具。它主要用于开发测试、课堂演示兜底和无网络调试，不代表完整在线 Agent 体验。
