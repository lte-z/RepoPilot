# 配置参考

RepoPilot 的配置分为两类：YAML 配置和环境变量。YAML 负责权限、工具行为和运行限制；环境变量负责 LLM 服务连接。默认运行时数据保存在 RepoPilot home，不会写入被分析仓库。默认文件由 `repopilot setup` 或首次运行 `repopilot` 自动生成。

```text
REPOPILOT_HOME/
  config.yaml
  .env
  repos/
    <repo-id>/
      profile.yaml
      reports/
```

`config.yaml` 和 `.env` 属于全局配置；`repos/<repo-id>/profile.yaml` 保存单个仓库的 profile，包括仓库路径和报告目录。RepoPilot 默认不会在目标仓库中创建 `.repopilot/`。

默认报告保存在对应仓库 profile 的 `reports/` 目录中；顶层 `reports/` 不再作为常规保存位置主动创建。

默认 home 位置遵循平台习惯：

| 平台 | 默认位置 |
|---|---|
| Windows | `%APPDATA%\RepoPilot` |
| macOS | `~/Library/Application Support/RepoPilot` |
| Linux | `$XDG_CONFIG_HOME/repopilot` 或 `~/.config/repopilot` |

可以通过 `REPOPILOT_HOME` 指定自定义目录。`REPOPILOT_PROJECT_ROOT` 是旧版兼容入口，不建议新配置继续使用。

## YAML 配置

默认加载顺序：

1. CLI `--config` 指定的路径。
2. 环境变量 `REPOPILOT_CONFIG`。
3. `REPOPILOT_HOME/config.yaml`。

相对路径会以配置文件所在目录为基准解析。

`--config` 和 `REPOPILOT_CONFIG` 只影响 YAML 配置。LLM 供应商、Base URL、模型和 API Key 始终从 `REPOPILOT_HOME/.env` 读取，也可以被同名系统环境变量覆盖。

### `permissions`

控制 RepoPilot 能读取和写入哪些位置。

| 字段 | 类型 | 说明 |
|---|---|---|
| `allow_all_roots` | boolean | 是否允许选择任意仓库路径。默认运行时配置为 `false`。 |
| `respect_git_ignore` | boolean | Git 仓库中是否遵循 `.gitignore`、`.git/info/exclude` 和 Git 标准忽略规则。 |
| `readable_roots` | list[string] | 可选择仓库所在的白名单根目录。CLI/WebUI 的 session repo 必须位于这些根目录内。 |
| `writable_roots` | list[string] | RepoPilot 可写入的目录，默认用于保存 Markdown 报告。 |
| `deny_patterns` | list[string] | 安全拒绝规则，适合放 `.env`、`.git`、虚拟环境等不应被工具读取的路径。 |
| `fallback_ignore_patterns` | list[string] | 非 Git 仓库的默认忽略规则，适合放构建产物、缓存、依赖目录等噪声路径。 |

Git 仓库优先遵循 Git 自己的可见文件规则。`fallback_ignore_patterns` 只在非 Git 仓库或 `respect_git_ignore=false` 时作为回退规则使用。

### `execution`

预留给未来的命令执行工具。当前版本不提供命令执行 MCP 工具。

| 字段 | 类型 | 说明 |
|---|---|---|
| `allow_command_execution` | boolean | 是否允许未来的命令执行工具运行外部命令。 |
| `allowed_commands` | list[string] | 未来命令执行工具的命令白名单。 |

### `intent`

控制自然语言输入进入仓库工具前的意图识别节点。

| 字段 | 类型 | 说明 |
|---|---|---|
| `use_llm_router` | boolean | 是否默认使用 LLM Intent Router。关闭后使用本地规则回退。 |
| `fallback_to_rules` | boolean | Intent Router 超时、配置缺失、JSON 无效或置信度过低时，是否回退到本地规则。 |
| `min_confidence` | number | LLM 意图识别最低置信度，低于该值时触发回退或澄清。 |
| `max_prompt_context_chars` | integer | 传给 Intent Router 的历史上下文最大字符数。 |

`/` 开头的命令不会进入 Intent Router；该配置只影响普通自然语言输入。

### `network`

控制联网文本抓取工具 `web_fetch_url`。

| 字段 | 类型 | 说明 |
|---|---|---|
| `allow_http_fetch` | boolean | 是否启用 HTTP(S) 文本抓取。 |
| `allowed_domains` | list[string] | 允许抓取的域名。空列表表示不限制公网域名。 |
| `deny_private_hosts` | boolean | 是否拒绝 localhost、私网地址和链路本地地址。 |
| `timeout_seconds` | number | 单次 URL 请求超时时间。 |
| `max_fetch_chars` | integer | 单次联网工具最多返回的字符数。 |

### `ui`

控制 CLI 的显示行为。WebUI 不依赖这些配置。

| 字段 | 类型 | 说明 |
|---|---|---|
| `animations` | boolean | 是否在真实终端中显示 spinner。非 TTY、`--json` 和测试环境会自动使用普通日志输出。 |
| `show_user_turns` | boolean | 是否在用户输入后额外显示 `You` 分隔面板。 |
| `keep_progress_log` | boolean | 是否在每轮完成后保留压缩后的工具/模型进度 Trace。 |
| `logo` | string | 启动页 Logo 风格。当前支持 `compact` 和 `none`。 |
| `compact_width` | integer | 小于该终端宽度时使用紧凑布局。 |

### `limits`

控制工具和 Agent 编排的资源上限。

| 字段 | 类型 | 说明 |
|---|---|---|
| `max_file_chars` | integer | 单文件读取最多返回的字符数。 |
| `max_search_results` | integer | 文本搜索最多返回的匹配条数。 |
| `max_tree_entries` | integer | 目录树最多返回的条目数量。 |
| `max_tool_rounds` | integer | Agent 最多进行的工具调用轮次。 |
| `llm_timeout_seconds` | number | 单次 LLM 请求超时时间。 |
| `tool_timeout_seconds` | number | 单次 MCP 工具调用超时时间。 |
| `intent_timeout_seconds` | number | 单次 LLM Intent Router 请求超时时间。 |
| `max_context_artifacts` | integer | 多轮对话中最多注入多少份历史报告摘要。 |
| `max_repeated_tool_calls` | integer | 相同工具和相同参数允许重复调用的次数，超过后跳过。 |

### `modes`

控制各分析模式的模型、工具权限和工具轮次预算。`modes.<mode>.model` 为空时使用全局 `LLM_MODEL`；`modes.<mode>.max_tool_rounds` 为空时使用 `limits.max_tool_rounds`。

已内置模式：

| 模式 | 说明 |
|---|---|
| `overview` | 仓库用途、技术栈、关键目录和重要文件概览。 |
| `runbook` | 安装、运行、测试、构建线索。 |
| `module-map` | 目录职责、入口文件、核心模块关系，默认可使用 `repo_symbol_map`。 |
| `task-brief` | 围绕任务搜索相关文件、阅读顺序和风险点，默认可使用 `repo_symbol_map`。 |
| `deep-scan` | 完整仓库入职包，整合概览、模块、符号、运行线索和风险。 |

每个模式支持：

| 字段 | 类型 | 说明 |
|---|---|---|
| `model` | string/null | 该模式单独使用的模型名。 |
| `max_tool_rounds` | integer/null | 该模式最多工具调用轮次。 |
| `enabled_tools` | list[string] | 该模式暴露给 LLM 的 MCP 工具列表。 |

## 环境变量

`REPOPILOT_HOME/.env` 保存 OpenAI-compatible 连接项：

| 变量 | 说明 |
|---|---|
| `LLM_PROVIDER` | 供应商显示名，例如 `DeepSeek`、`OpenAI` 或自定义名称。 |
| `LLM_BASE_URL` | OpenAI-compatible API base URL。 |
| `LLM_API_KEY` | LLM API Key。不要提交到 Git。 |
| `LLM_MODEL` | Chat Completion 模型名。 |

已有 API Key 时，交互式命令会先确认是否覆盖；取消或提交空值都会保留旧值。

内置 Provider 预设按常见使用顺序排列；没有列出的 OpenAI-compatible 服务可以选择自定义供应商。

| 别名 | Provider | Base URL | 默认模型 |
|---|---|---|---|
| `openai` | OpenAI | `https://api.openai.com/v1` | `gpt-5-mini` |
| `gemini` | Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai/` | `gemini-2.5-flash` |
| `deepseek` | DeepSeek | `https://api.deepseek.com` | `deepseek-v4-flash` |
| `qwen` | Alibaba Qwen / DashScope | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| `kimi` | Moonshot Kimi | `https://api.moonshot.cn/v1` | `kimi-k2.5` |
| `zhipu` | Zhipu GLM | `https://open.bigmodel.cn/api/paas/v4/` | `glm-5.1` |
| `openrouter` | OpenRouter | `https://openrouter.ai/api/v1` | `openrouter/auto` |
| `groq` | Groq | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` |
| `siliconflow` | SiliconFlow | `https://api.siliconflow.cn/v1` | `deepseek-ai/DeepSeek-V3` |

Anthropic Claude 原生 API 不在内置直连列表中，因为 RepoPilot 当前使用 OpenAI-compatible Chat Completions 客户端；如需使用 Claude，可通过 OpenRouter 或其他 OpenAI-compatible 网关接入。

## CLI 配置入口

当前 CLI 已提供以下配置入口：

```bash
repopilot setup
repopilot config doctor
repopilot config show
repopilot config list
repopilot config schema
repopilot config get limits.max_tool_rounds
repopilot config set limits.max_tool_rounds 12
repopilot config set intent.use_llm_router true
repopilot config set intent.min_confidence 0.6
repopilot config set modes.deep-scan.max_tool_rounds 12
repopilot config set modes.module-map.enabled_tools '["repo_list_tree", "repo_detect_stack", "repo_symbol_map"]'
repopilot config set ui.animations false
repopilot config set ui.keep_progress_log true
repopilot config set ui.logo none
repopilot config reset limits.max_tool_rounds
repopilot config set-provider
repopilot config set-api-key
repopilot config add-root /path/to/repos
repopilot config remove-root /path/to/repos
repopilot config network on
repopilot config network off
repopilot mcp
repopilot mcp on
repopilot mcp off
```

会话内也可以使用 `/settings`、`/settings get`、`/settings set` 和 `/settings reset` 修改同一份 YAML 配置。

`config set` 的值按 YAML 解析，适合设置布尔值、数字和列表：

```bash
repopilot config set network.allow_http_fetch false
repopilot config set network.allowed_domains '["docs.python.org", "github.com"]'
repopilot config set permissions.fallback_ignore_patterns '["**/dist/**", "**/node_modules/**"]'
```

这些配置入口应继续遵循当前原则：默认只读、显式授权、用户运行时配置只写入 RepoPilot home。
