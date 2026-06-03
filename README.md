# RepoPilot

RepoPilot 是一个面向陌生代码仓库的只读优先 MCP 入职侦察 Agent。它适合在克隆一个项目之后、正式编码之前使用：先读取仓库结构、依赖线索、Git 元数据和任务相关文件，再生成仓库概览、运行手册、模块地图或任务简报。

RepoPilot 的目标不是替代通用编码 Agent，而是把“进入陌生仓库前的侦察工作”做成一个边界清晰、可复用、可演示的单用途 Agent。

## 功能

- `overview`：生成仓库用途、技术栈、关键目录和重要文件概览。
- `runbook`：推断安装、运行、测试和构建方式。
- `module-map`：梳理目录职责、入口文件和核心模块。
- `task-brief`：根据具体任务搜索相关文件，给出阅读顺序和风险点。
- MCP 工具：通过 FastMCP 暴露仓库树、文件读取、全文搜索、技术栈识别、Git 摘要、联网文本抓取和报告保存工具。
- 双入口：CLI 面向真实开发流程，WebUI 面向演示和可视化浏览。

## 架构

```text
src/repopilot/
  config.py          # 配置和环境变量加载
  permissions.py     # 路径白名单、会话仓库边界和拒绝规则
  tools/             # 仓库侦察工具
  mcp_server.py      # FastMCP stdio 服务
  agent.py           # OpenAI 兼容的工具调用编排循环
  cli.py             # Typer + Rich 命令行入口
  web.py             # 本地 FastAPI WebUI
docs/
  configuration.md   # 配置项、权限边界和未来配置界面参考
```

## 安装

RepoPilot 需要 Python 3.12 或更高版本。

```bash
git clone https://github.com/lte-z/RepoPilot.git
cd RepoPilot
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
cp config.example.yaml config.yaml
cp .env.example .env
```

Windows 用户可以用 `.venv\Scripts\activate` 激活虚拟环境。

## 使用

无需 API Key 时，可以先使用离线模式验证本地工具链：

```bash
repopilot overview . --offline
```

配置 `.env` 中的 `LLM_API_KEY` 后，可以运行完整 Agent：

```bash
repopilot overview /path/to/repo
repopilot runbook /path/to/repo
repopilot module-map /path/to/repo
repopilot task-brief /path/to/repo "分析登录流程"
```

保存 Markdown 报告：

```bash
repopilot overview /path/to/repo --save
```

启动本地 WebUI：

```bash
repopilot web
```

## 权限模型

RepoPilot 使用“父目录白名单 + session repo”模型。配置文件中的 `readable_roots` 决定可选择仓库所在的父目录；每次 CLI/WebUI 调用会指定一个具体仓库路径，工具只能读取该仓库内部内容。写权限默认只允许 `outputs/`，并通过 `deny_patterns` 拒绝 `.env`、`.git`、虚拟环境等敏感或边界路径。

配置为 `writable_roots` 的目录会被视为 RepoPilot 运行产物目录。目录树、全文搜索和技术栈识别会跳过这些目录，避免已保存报告反过来污染仓库侦察结果。

如果目标仓库是 Git 仓库，RepoPilot 会优先遵循 Git 的可见文件规则：`repo_list_tree`、`repo_search_text`、`repo_detect_stack` 和 `repo_read_file` 会尊重 `.gitignore`、`.git/info/exclude` 以及 Git 标准忽略规则。非 Git 仓库会回退到 `fallback_ignore_patterns`，该列表在 `config.yaml` 中透明可编辑。

第一版不实现命令执行工具，`allow_command_execution` 与 `allowed_commands` 仅作为后续扩展的配置门。

## MCP 工具

RepoPilot 通过本地 stdio MCP server 暴露以下工具：

- `repo_list_tree`
- `repo_read_file`
- `repo_search_text`
- `repo_detect_stack`
- `repo_git_summary`
- `repo_save_report`
- `web_fetch_url`

`repo_search_text` 会优先调用 `rg` 以获得更快的搜索速度；如果本机未安装 ripgrep，会自动退回到内置文本搜索。

`web_fetch_url` 用于读取公开 HTTP(S) 文本内容，例如官方文档、README 原文或包管理页面。该工具受 `network` 配置控制，默认拒绝访问 localhost 和私网地址。

## 配置

默认配置文件为 `config.example.yaml`。推荐复制为本地 `config.yaml` 后修改：

```bash
cp config.example.yaml config.yaml
```

公开模板默认只允许读取 RepoPilot 仓库自身。若要分析其他仓库，请修改本地 `config.yaml`，将 `readable_roots` 改为目标仓库所在的父目录，例如 `D:/Code` 或 `/home/you/src`。`config.yaml` 会被 Git 忽略，适合保存个人路径。

完整配置项见 [docs/configuration.md](docs/configuration.md)。

`.env.example` 默认使用 OpenAI 兼容接口配置：

```dotenv
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=
LLM_MODEL=deepseek-v4-flash
REPOPILOT_CONFIG=./config.yaml
```

## 开发

```bash
pytest
python -m repopilot.mcp_server
```

## 许可证

MIT
