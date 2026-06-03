# 配置参考

RepoPilot 的配置分为两类：本地 YAML 配置和环境变量。YAML 负责权限、工具行为和运行限制；环境变量负责 LLM 服务连接。公开仓库只提供 `config.example.yaml` 和 `.env.example`，个人路径、API Key 和本地偏好应写入被 Git 忽略的 `config.yaml` 与 `.env`。

## YAML 配置

默认加载顺序：

1. CLI `--config` 指定的路径。
2. 环境变量 `REPOPILOT_CONFIG`。
3. 项目内 `config.example.yaml`。

相对路径会以配置文件所在目录为基准解析。

### `permissions`

控制 RepoPilot 能读取和写入哪些位置。

| 字段 | 类型 | 说明 |
|---|---|---|
| `allow_all_roots` | boolean | 是否允许选择任意仓库路径。公开模板默认为 `false`。 |
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

### `network`

控制联网文本抓取工具 `web_fetch_url`。

| 字段 | 类型 | 说明 |
|---|---|---|
| `allow_http_fetch` | boolean | 是否启用 HTTP(S) 文本抓取。 |
| `allowed_domains` | list[string] | 允许抓取的域名。空列表表示不限制公网域名。 |
| `deny_private_hosts` | boolean | 是否拒绝 localhost、私网地址和链路本地地址。 |
| `timeout_seconds` | number | 单次 URL 请求超时时间。 |
| `max_fetch_chars` | integer | 单次联网工具最多返回的字符数。 |

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

## 环境变量

`.env.example` 提供 OpenAI-compatible 默认项：

| 变量 | 说明 |
|---|---|
| `LLM_BASE_URL` | OpenAI-compatible API base URL。 |
| `LLM_API_KEY` | LLM API Key。不要提交到 Git。 |
| `LLM_MODEL` | Chat Completion 模型名。 |
| `REPOPILOT_CONFIG` | 本地 YAML 配置路径。 |

## 未来配置界面

后续 CLI/WebUI 可以围绕以下操作提供图形化或交互式配置入口：

- 添加、移除、查看 `readable_roots`。
- 添加、移除、查看 `writable_roots`。
- 切换 `respect_git_ignore`。
- 编辑 `fallback_ignore_patterns`。
- 切换 `allow_http_fetch`，维护 `allowed_domains`。
- 调整 `max_file_chars`、`max_search_results`、`max_tree_entries` 和超时时间。
- 配置 LLM provider、base URL、模型名和 API Key。
- 启用未来的命令执行工具，并维护 `allowed_commands`。

这些配置入口应继续遵循当前原则：默认只读、显式授权、个人配置只写入本地忽略文件。
