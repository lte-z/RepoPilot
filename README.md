# RepoPilot

RepoPilot 是一个面向陌生代码仓库的只读优先 MCP 入职侦察 Agent。它适合在克隆一个项目之后、正式编码之前使用：先读取仓库结构、依赖线索、Git 元数据和任务相关文件，再生成仓库概览、运行手册、模块地图或任务简报。

[![CI](https://github.com/lte-z/RepoPilot/actions/workflows/ci.yml/badge.svg)](https://github.com/lte-z/RepoPilot/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

RepoPilot 的目标不是替代通用编码 Agent，而是把“进入陌生仓库前的侦察工作”做成一个边界清晰、可复用、可审计、可维护的单用途 Agent。

## 功能

- `overview`：生成仓库用途、技术栈、关键目录和重要文件概览。
- `runbook`：推断安装、运行、测试和构建方式。
- `module-map`：梳理目录职责、入口文件和核心模块。
- `task-brief`：根据具体任务搜索相关文件，给出阅读顺序和风险点。
- `deep-scan`：生成完整仓库入职包，整合概览、运行线索、模块地图、符号地图和风险提示。
- LLM Intent Router：普通自然语言先识别意图，只有需要仓库证据时才调用 MCP 工具。
- MCP 工具：通过 FastMCP 暴露仓库树、文件读取、全文搜索、技术栈识别、符号地图、Git 摘要、联网文本抓取和报告保存工具。
- CLI 驾驶舱：提供状态卡片、快速动作、用户输入分隔、终端宽度自适应和可关闭的 spinner。
- CLI 驾驶舱是主入口；预览版本地 WebUI 可用于快速查看一次性分析和报告预览。

## 架构

```text
src/repopilot/
  config.py          # 配置和环境变量加载
  permissions.py     # 路径白名单、会话仓库边界和拒绝规则
  tools/             # 仓库侦察工具
  mcp_server.py      # FastMCP stdio 服务
  agent.py           # OpenAI 兼容的工具调用编排循环
  session.py         # 多轮会话状态和 quick action 编排
  cli.py             # Typer + Rich 命令行入口
  web.py             # 预览版本地 FastAPI WebUI
docs/
  cli-reference.md   # CLI 与会话命令完整清单
  configuration.md   # 配置项、权限边界和配置命令参考
```

## 安装

RepoPilot 需要 Python 3.12 或更高版本。

普通用户可以直接从 GitHub 安装。安装后，`pip` 会为当前 Python 环境生成 `repopilot` 命令，首次运行会自动初始化 `.repopilot/`。

安装稳定发布版：

```bash
python -m pip install git+https://github.com/lte-z/RepoPilot.git@v0.1.0
repopilot
```

安装 `main` 分支最新状态：

```bash
python -m pip install git+https://github.com/lte-z/RepoPilot.git
repopilot
```

如果已经安装过，建议加上 `--upgrade` 更新：

```bash
python -m pip install --upgrade git+https://github.com/lte-z/RepoPilot.git@v0.1.0
```

如果终端提示找不到 `repopilot`，通常是 Python 的 `Scripts` 目录不在 PATH。Windows 上可以先查看：

```bash
python -m site --user-base
```

然后将输出目录下的 `Scripts` 子目录加入 PATH，例如：

```text
%APPDATA%\Python\Python312\Scripts
```

也可以直接使用模块方式运行：

```bash
python -m repopilot.cli
```

可选：如果已安装 `pipx` 或 `uv`，也可以使用隔离式安装：

```bash
pipx install git+https://github.com/lte-z/RepoPilot.git
uv tool install git+https://github.com/lte-z/RepoPilot.git
```

开发者安装：

```bash
git clone https://github.com/lte-z/RepoPilot.git
cd RepoPilot
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

如果移动或复制 RepoPilot 仓库，请在新位置重新创建 `.venv` 并重新安装依赖。虚拟环境和可编辑安装通常包含绝对路径，不适合直接复制。

## 使用

安装后直接运行：

```bash
repopilot
```

RepoPilot 会进入引导式 CLI：初始化本地配置、选择 LLM 供应商、提示是否填写 API Key、选择要分析的仓库路径，然后直接进入多轮仓库会话。用户不需要先手动阅读配置文件或记住一组命令。

运行时配置默认保存在当前工作目录内被 Git 忽略的 `.repopilot/`：

```text
.repopilot/
  config.yaml   # 权限、网络和工具限制
  .env          # LLM provider、模型和 API Key
  reports/      # 保存的 Markdown 报告
```

会话内支持：

```text
/help
/help chat
/overview
/runbook
/module-map
/task-brief <task>
/deep-scan
/mcp [on|off]
/sources
/artifacts
/save [name]
/config
/settings [get|set|reset]
/provider
/api-key
/status
/clear
/exit
```

以 `/` 开头的输入只按命令解析；普通自然语言默认先进入 LLM Intent Router，只有确实需要仓库证据时才调用 MCP 工具。完整命令清单见 [docs/cli-reference.md](docs/cli-reference.md)。

如果想绕过引导，直达指定仓库：

```bash
repopilot chat /path/to/repo
```

无需 API Key 时，可以使用离线模式验证本地工具链：

```bash
repopilot chat /path/to/repo --offline
```

`--offline` 主要用于开发测试、无网络调试和本地工具链检查；完整 Agent 体验默认使用在线 Intent Router 和在线模型回复。

一次性分析命令适合脚本化或快速生成单份报告：

```bash
repopilot overview /path/to/repo
repopilot runbook /path/to/repo
repopilot module-map /path/to/repo
repopilot task-brief /path/to/repo "分析登录流程"
repopilot deep-scan /path/to/repo
```

保存 Markdown 报告：

```bash
repopilot overview /path/to/repo --save
```

输出机器可读 JSON：

```bash
repopilot overview /path/to/repo --json
repopilot deep-scan /path/to/repo --json
```

查看或修改本地配置：

```bash
repopilot config doctor
repopilot config show
repopilot config list
repopilot config get limits.max_tool_rounds
repopilot config set limits.max_tool_rounds 12
repopilot config set intent.use_llm_router true
repopilot config set ui.animations false
repopilot config set ui.keep_progress_log true
repopilot config add-root /path/to/repos
repopilot mcp
repopilot mcp off
```

启动预览版本地 WebUI：

```bash
repopilot web
```

WebUI 目前用于本地预览一次性分析、工具调用时间线和报告预览；完整的多轮会话、配置管理和细粒度控制以 CLI 为准。

## 权限模型

RepoPilot 使用“父目录白名单 + session repo”模型。`.repopilot/config.yaml` 中的 `readable_roots` 决定可选择仓库所在的父目录；每次 CLI 或预览版 WebUI 调用会指定一个具体仓库路径，工具只能读取该仓库内部内容。写权限默认只允许 `.repopilot/reports/`，并通过 `deny_patterns` 拒绝 `.env`、`.git`、虚拟环境等敏感或边界路径。

配置为 `writable_roots` 的目录会被视为 RepoPilot 运行产物目录。目录树、全文搜索和技术栈识别会跳过这些目录，避免已保存报告反过来污染仓库侦察结果。

如果目标仓库是 Git 仓库，RepoPilot 会优先遵循 Git 的可见文件规则：`repo_list_tree`、`repo_search_text`、`repo_detect_stack` 和 `repo_read_file` 会尊重 `.gitignore`、`.git/info/exclude` 以及 Git 标准忽略规则。非 Git 仓库会回退到 `fallback_ignore_patterns`，该列表在 `config.yaml` 中透明可编辑。

第一版不实现命令执行工具，`allow_command_execution` 与 `allowed_commands` 仅作为后续扩展的配置门。

## MCP 工具

RepoPilot 通过本地 stdio MCP server 暴露以下工具：

- `repo_list_tree`
- `repo_read_file`
- `repo_search_text`
- `repo_detect_stack`
- `repo_symbol_map`
- `repo_git_summary`
- `repo_save_report`
- `web_fetch_url`

`repo_search_text` 会优先调用 `rg` 以获得更快的搜索速度；如果本机未安装 ripgrep，会自动退回到内置文本搜索。

`web_fetch_url` 用于读取公开 HTTP(S) 文本内容，例如官方文档、README 原文或包管理页面。该工具受 `network` 配置控制，默认拒绝访问 localhost 和私网地址。

## 配置

运行时配置统一保存在 `.repopilot/`，不会写入系统用户目录。默认配置由 `repopilot setup` 或首次运行 `repopilot` 自动生成。

如果需要从其他目录启动但仍希望把运行时配置写入某个固定项目目录，可以设置 `REPOPILOT_PROJECT_ROOT`。

默认本地配置会把启动目录加入可读白名单。若要分析其他位置的仓库，可以用 CLI 将目标仓库或其父目录加入白名单：

```bash
repopilot config add-root /path/to/repos
```

完整配置项见 [docs/configuration.md](docs/configuration.md)。

LLM 供应商、Base URL、模型和 API Key 由 `repopilot` 引导式入口、`/provider`、`/api-key` 或 `repopilot config set-provider` 写入 `.repopilot/.env`。`--config` 只指定 YAML 配置文件；LLM 连接信息仍来自当前运行目录或 `REPOPILOT_PROJECT_ROOT` 下的 `.repopilot/.env`。

## 开发

```bash
pytest
python -m build
python -m repopilot.mcp_server
```

## 许可证

MIT
