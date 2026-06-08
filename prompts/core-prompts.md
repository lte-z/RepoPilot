# 核心 Prompt 摘录

本文档按开发阶段整理 RepoPilot 开发过程中与 Codex 协作的核心 prompt。内容尽可能保留原始表达，只删除或省略以下内容：API Key、私人路径、与 RepoPilot 无关的个人工作区信息、过长调试日志和重复性对话。

这些 prompt 用于说明：RepoPilot 并不是一次性生成出来的模板项目，而是在明确实验要求后，通过多轮需求讨论、架构约束、交互打磨和质量复核逐步形成的单用途 Agent。

## 阶段 1：实验要求与项目目标

### 用户核心 Prompt 摘录

```text
我正在完成北京邮电大学课程“软件产品综合研发实践（阶段一）”的实验二。实验的全部要求如下：

Experiment: "Bring Your Own Agent" (BYOA)
You will use vibe coding (via Cursor, Codex, etc) to rapidly scaffold and deploy a custom, single-purpose AI agent. The agent can do whatever the student wants—from summarizing local PDF readings to checking their calendar and drafting emails—as long as it relies on external tools and context rather than just the LLM's base knowledge.

The Technical Requirements (The "Must-Haves")
The agent must successfully implement the following architectural components:
Tool Use / Skills: The agent must be equipped with at least two distinct functional skills (e.g., fetching a web page, querying a database, parsing a CSV, calling an external weather API).
Context Integration (MCP or similar): You must use a standardized protocol like MCP (Model Context Protocol) or standard LLM function calling to bridge the agent's brain with the local environment or APIs.
The "Vibe Coding" Constraint: You must use AI to write the boilerplate (e.g., the MCP server setup, the Pydantic models for function arguments, or the API request logic) so you can focus entirely on the agent's system prompt and orchestration loop.

Due：2026/06/20 23:59:59

Deliverables:
1. Code Repository (Agent logic and tool definitions)
2. Brief Report (no more than 5 pages including 3~4 execution screenshots and a short reflection of using AI in your development)

Evaluation:
System Mechanics & Tooling (Code Repo including all prompts) - 40 Points.
Agent Execution (Report Screenshots) - 40 Points
Your Reflection (Report Text) - 20 Points
A concise, honest reflection identifying a specific technical hurdle the AI faced (e.g., struggling with the protocol syntax, hallucinating arguments, etc.) and exactly how you engineered you way out of it.

我目前还没有拿到实验报告模板，但我认为先完成项目的工程部分再撰写报告也完全来得及（毕竟信息不会丢失 包括我们的聊天记录 包括创建的文件之类的）。
现在，请你仔细阅读以上全部要求，理解该实验的内容，并 Plan 一下项目的具体实施方案。这一过程中你必须向我提问以解决你的疑问并收集必要信息。这一轮对话不需要编辑任何文件。
```

### Codex 协作结果摘要

- 先从实验约束出发确认项目必须包含：至少两个工具技能、MCP 或函数调用式上下文集成、AI 辅助生成工程样板与编排逻辑。
- 将“先做工程、后写报告”作为工作节奏，避免为了报告倒推一个最低限度 demo。
- 后续选题逐步收敛到“面向陌生代码仓库的只读优先 MCP 入职侦察 Agent”。

## 阶段 2：选题形成：从开源贡献经历到仓库侦察 Agent

### 用户核心 Prompt 摘录

```text
我想我们还要再探讨一会儿选题。是这样，如果只针对我的个人 Monorepo，那这个 Agent 完全没用啊？只运行一次，这个仓库的报告保存下来，后面几乎不会再用了。并且考虑到不是每个程序开发者都有这样的 Monorepo 的，对吧？我们如果做一个仓库探测工具，对任意仓库都可以做整理 + 做报告或者做各种各样的功能，这样是不是会更好？话又说回来，因为我平时是 OpenCode 的重度使用者，感觉这种读仓库的工作一般是开发的前置工作（比如说我今天拉下来一个仓库 我要为其做贡献 那么第一件事儿是让 Agent 先分析一下 然后再开始工作），配置一个单独的任务或者命令什么的就能完成了。为此工作开发一个 Agent 是不是其实实用性有些弱？
```

```text
我感觉 RepoPilot 这个有点眉目了，好像选题可以不用大改了？引入这个 Agent 的场景就是，我们这个课程的实验一要求给别人的开源项目做贡献，然后我给 microsoft/vscode-documentdb 仓库交了三个 PR。工作的过程中我意识到需要一个 Agent 做这个读仓库的前置工作，大概这样？

你去把该读的信息都读了，该拿的信息都拿到。下一轮 Plan 做准备工作的收尾，你需要输出完整的项目概念和规划之类的信息。然后，做开始项目前在创建项目时的 Plan 工作（比如说去哪建什么文件夹 改哪些文件 使用什么顺序）。
有问题立刻停下来问我，不要主观臆断。
```

### Codex 协作结果摘要

- 选题从“分析个人代码仓库”调整为“任意陌生仓库的前置理解工具”，避免项目只服务一次性个人场景。
- 明确产品场景：开发者克隆一个开源仓库、准备贡献代码之前，先让 Agent 读取结构、依赖、Git 状态和任务相关文件，生成入职简报。
- RepoPilot 的定位由此确定：不是通用编码 Agent，而是“只读优先”的仓库侦察 Agent。

## 阶段 3：RepoPilot 工程计划与 MCP 架构

### 用户核心 Prompt 摘录

```text
PLEASE IMPLEMENT THIS PLAN:
# RepoPilot 项目开发计划

## Summary

RepoPilot 定位为“面向陌生代码仓库的只读优先 MCP 入职侦察 Agent”，用于在正式编码前生成仓库概览、运行手册、模块地图和任务简报。项目服务于 BYOA 实验要求：至少两个工具技能、MCP / 函数调用上下文集成、AI 辅助生成工程样板与编排循环，并最终提供 CLI + WebUI 双入口。

README 和用户可见文档默认中文，代码标识符、CLI 命令、配置键保持英文。

## Implementation Changes

- 基础工程
  - 使用 Python 3.12+、独立 `.venv`、`pyproject.toml` 管理依赖。
  - 将现有英文 scaffold README 改为中文正式 README，保留 MIT License。
  - 代码采用 `src/repopilot/` 包结构，按 `config / permissions / tools / mcp_server / agent / cli / web` 分层。
  - `.env.example` 继续使用 OpenAI-compatible 配置，默认 DeepSeek：
    - `LLM_BASE_URL=https://api.deepseek.com`
    - `LLM_MODEL=deepseek-v4-flash`

- 权限与配置
  - 采用“父目录白名单 + session repo”模型。
  - 配置文件定义 `readable_roots`、`writable_roots`、`deny_patterns`、`limits`。
  - CLI / WebUI 每次选择一个具体仓库路径作为 `session_repo`，工具只能读取该仓库内部内容。
  - 写权限默认只允许 `outputs/`。
  - 第一版不实现命令执行工具，只保留配置门：
    - `allow_command_execution`
    - `allowed_commands`
  - 默认拒绝读取 `.env`、`.git`、`.venv`、`node_modules`、`__pycache__` 等路径。

- MCP 工具
  - 使用 MCP Python SDK / FastMCP，本地 stdio transport。
  - 实现以下只读工具：
    - `repo_list_tree`：返回带深度和数量限制的目录树。
    - `repo_read_file`：读取单个文本文件，受大小限制和 deny patterns 约束。
    - `repo_search_text`：基于 `rg` 搜索文本，支持 glob 和结果数量限制。
    - `repo_detect_stack`：识别项目技术栈、依赖文件、脚本入口和常见构建线索。
    - `repo_git_summary`：只读读取分支、remote、最近提交、status、diff stat。
    - `repo_save_report`：把最终 Markdown 报告保存到 RepoPilot 的 `outputs/`。
  - 每个工具使用 Pydantic 输入模型、清晰 docstring、可行动错误信息和 MCP annotations。

- Agent Core
  - 实现手动 tool-calling orchestration loop：
    - 加载中文 system prompt。
    - 连接 MCP server。
    - 把 MCP tools 暴露给 OpenAI-compatible chat completion。
    - 执行 tool calls 并回填结果。
    - 限制最大工具轮次，默认 `max_tool_rounds=8`。
  - 内置四种分析模式：
    - `overview`：仓库概览。
    - `runbook`：安装、运行、测试、构建线索。
    - `module-map`：目录职责、入口文件、核心模块。
    - `task-brief`：针对用户任务搜索相关文件并给阅读顺序。
  - 输出结构固定为中文 Markdown，包含“结论、证据、建议下一步”。

- CLI
  - 使用 Typer + Rich，CLI 先稳。
  - 命令接口：
    - `repopilot overview <repo_path>`
    - `repopilot runbook <repo_path>`
    - `repopilot module-map <repo_path>`
    - `repopilot task-brief <repo_path> "<task>"`
    - `repopilot web`
  - CLI 展示工具调用时间线、耗时、结果摘要和最终 Markdown。
  - 支持 `--save` 保存报告，支持 `--config` 指定配置文件。

- WebUI
  - 使用 FastAPI + 原生 HTML / CSS / JS，不拆 Vue / Vite 子项目。
  - WebUI 复用 Agent Core，不重新实现逻辑。
  - 页面能力：
    - 输入或选择仓库路径。
    - 选择分析模式。
    - 输入 task brief 的任务文本。
    - 展示工具调用时间线。
    - 预览最终 Markdown。
    - 保存报告。
  - 视觉设计后置到核心功能稳定后处理，不强制延续 Catppuccin Mocha，但保留“开发者驾驶舱”的信息密度和质感方向。
```

### Codex 协作结果摘要

- 按该计划搭建 Python 项目结构、MCP server、工具定义、Agent 编排、CLI 命令和测试框架。
- 工具能力覆盖本地仓库结构读取、文件读取、文本搜索、技术栈识别、Git 摘要、报告保存，并补充了联网抓取工具开关。
- 编排层采用 OpenAI-compatible API，模型供应商可配置，默认适配 DeepSeek。

## 阶段 4：权限、安全与配置边界

### 用户核心 Prompt 摘录

```text
.venv 是一个很危险的操作，如果操作不当，极易把各种包安装到我本机的外部环境中，这是必须严格禁止的。所以这后面针对 venv 的部分你应该严谨工作。
另外我有注意到一些问题，比如说作为 public repository，你在 README.md 里居然直接写了我本机的绝对路径，这是不可容忍的。你不能保证你目前为止的代码和文档质量没有问题，所以我感觉还需要一些检查。
```

```text
目前接入 DeepSeek 运行得很好啊，不过 UI 显示还有很大提升空间，但那后面再说。我现在有一些事情要提： 
我们目前写死的这些忽略文件夹（比如 build 之类的）太黑箱了。我理解的文件忽略应该这样处理：
1. 如果仓库内含 .gitignore，则完全遵循其内容。
2. 如果不含 .gitignore，则回退到写死的忽略项。但忽略项应该透明可编辑，作为配置文件的一部分，而不是直接写死。
另外，说到 .gitignore，我们的这个 Agent 工具应该会理解并完全遵循仓库内一切 git 相关的文件（如有），遵循其行为规则来应对各种情况。
再有，目前此 Agent 全部能力都限制在本地，没有任何联网的 MCP 之类的吗？我认为在这个方向应该引入一些新的能力吧？包括一些额外的 tool call 之类的。 
最后，这一阶段你认为还有任何值得优化的地方吗？你刚刚 debug 的时候有没有引入冗余元素。此项目是否除了显示效果优化之外没有提升空间了？此项目仓库是否干净整洁无冗余？确保做到这几点，然后才可以 commit 并 push。
```

```text
不好意思打断一下：
1. 我注意到 docs/ 目录目前为空，没有 .gitkeep 了。我认为是这样：如果项目还有文档要写，那你就现在立刻写了。如果确实没有文档要写了，则 docs/ 目录可以直接移除了。同步更新 README.md。
2. 我们可能需要有个地方记下来目前所有可改配置项。目前用户只能通过直接编辑文件来修改，但未来我们会在 CLI 和 WebUI 里面提供直接更改这些配置的地方，包括开关或添加 MCP 之类的。或许需要提前梳理出来？
3. 这之后，继续做那个最后一轮全量验证，确保文档、代码、配置文件等所有文件内容全都满足开源社区规范且质量上乘。包括没有写错的地方，没有冗余的地方，没有不该包含的地方（比如个人隐私、API Key 之类的），干净整洁又不失严谨等。
```

### Codex 协作结果摘要

- 移除公开文档中的本机绝对路径，避免把个人环境细节写进 public repository。
- 将忽略逻辑从“黑箱写死”调整为：优先尊重仓库 `.gitignore`，再回退到透明、可配置的默认忽略项。
- 文档补充配置项说明，仓库提交前进行隐私、API Key、临时文件和冗余内容扫描。
- 后续引入 `REPOPILOT_HOME` 存储模型和安全清理命令，降低 `.repopilot` 被误提交到他人仓库的风险。

## 阶段 5：CLI 体验与多轮 Agent 交互

### 用户核心 Prompt 摘录

```text
这两个界面你要怎么 Plan 一下？除了最基本的对话和工具调用，还要有什么功能显示在界面上？包括咱们做的这个 Agent 不应该是只使用命令聊一轮就结束（因为那样更倾向于是一个融合了 AI 的一次性小工具），而是可以有一些深度和上下文的。我们目前开发的那四个模式当然有用，但是 AI 也应该学会利用那些信息处理用户后续的需求。比如说某个对话内，用户先调用 overview 功能让 Agent 生成这部分的报告，这之后说不定还会继续追问，比如说哪里没懂之类的。或者甚至 Agent 本身把 overview~task-brief 这四个功能当做原生工具调用，用户如果只要求“分析仓库”，Agent 也会主动判断该调用哪些工具进行生成和回复。这方面的探讨值得展开的地方还很多，你觉得呢？
至于功能，我认为 CLI 和 WebUI 的功能不应该有出入，只不过前者基于终端，很多功能依赖简单的点击或者命令，而后者更美观易用一些。在开发 CLI 的时候，你看一下可不可以借鉴 OpenCode CLI 以及各家 Agent CLI 的风格；在开发 WebUI 的时候，当然也借鉴各家的软件风格。你应该做一个大的完整的 Plan，梳理出来要做哪些功能、交互逻辑等，以及如何实现。
```

```text
哦对，.env 和 config.yaml 是不是也应该支持通过 CLI 或者 WebUI 进行修改编辑？我认为理想状态下使用 CLI 或者 WebUI 的用户可以做到开箱即用，什么别的都不用配置了。比如说第一次打开软件就提示填写 API Key，或者在没有 API Key 的时候提示用户去某处填写之类的。底层文件所存储的配置统一到某个特定路径下，并且完全通过程序界面管理。你觉得这个想法怎么样？不过还得保证那些文件被 .gitignore 筛掉。
做最后一轮 Plan。
```

```text
一点一点挑问题：
1. 目前 CLI 的用户体验很不连贯啊，用户得手捧着 README.md 一点一点读才能了解这个项目如何运作，甚至读到文档的后半部分才能发现有一个 chat 模式。我认为这个思路是绝对错误的！应该用户只输入一条命令以某种方式进入 CLI，相当于就直接进入 chat 模式或者 chat 模式前的由 CLI 引导式 Setup 的地方啊？然后比如说 CLI 再提示你填 API Key，选择仓库路径之类的，把一系列引导工作都做好。绝对不应该让用户手捧着 README 一行一行敲也不知道在干嘛。
2. 你的 CLI 界面要善用 clear。你像我用 OpenCode 的时候，只需要输入命令 opencode 然后就可以进入沉浸的 OC 界面了。
3. 我测到这已经不想测试了，因为你思路有很多问题。还有一个目前发现是小问题是 /help 的输出中 /save           保存最近一份报告  这一行比其他行少了一次缩进。
```

```text
我继续提问：
1. 这怎么上来就默认用户一定用 DeepSeek 呢？在输入 API Key 之前先选择供应商吧。
2. 我发现你清屏用的不是 clear，因为我用鼠标滚轮往上滚还是能看到之前的历史记录。
3. 比如我输入 /overview，Agent 干活的时候怎么完全不提示自己在干啥呢？搞得还以为卡了似的，这一跑又跑半分钟。
4. 比如我输错了指令但是发出去了，你没提供一个打断功能啊。AI 又会陷入漫长无提示的处理阶段。
```

```text
1. 现在的 MCP 只能看状态不能改啊。包括如果想更改供应商 / API Key 之类的，是不是也没有提供显式的操作方法？
2. .repopilot\sessions 和 .repopilot\cache 都是干啥用的？我目前只发现 .repopilot\reports 有用了。好像每一轮跑完他自己就会生成报告，然后我如果使用 /save 又会保存一次？不过 /save 保存的报告不知道使用了什么非法的 Markdown 语法，总之显示效果有点儿问题。
3. 建议每轮对话之间多一个空行或者你加个框什么的，现在这样都混在一起有点儿乱。
4. 根目录下的 config.example.yaml、config.yaml、.env.example、.env 是不是完全没用了？我感觉也不应该再有用了。该保存的数据我都保存好了，这些文件如果没用就删。包括其他的文件也一样。这很不干净啊。
```

### Codex 协作结果摘要

- CLI 从“命令集合”调整为默认进入沉浸式会话：首次运行引导选择 provider、填写 API Key、选择仓库路径。
- 增加 `/help`、`/provider`、`/api-key`、`/mcp`、`/tools`、`/settings`、`/sources`、`/save`、`/clear` 等命令，并统一输出风格。
- 引入工具调用时间线、运行状态、分隔线、token 展示、会话标题、Quick Actions、Input / About 区域和版本号展示。
- 将 WebUI 降级为实验性入口，主体验聚焦 CLI。

## 阶段 6：Intent Router 与关键问题修正

### 用户核心 Prompt 摘录

```text
RepoPilot> 你还能做什么？
RepoPilot 处理追问。按 Ctrl+C 可尝试中断。
RepoPilot 启动本地 MCP server。
RepoPilot MCP server 已连接，正在读取工具列表。
RepoPilot 已加载 7 个 MCP 工具。
RepoPilot 第 1 轮：请求模型 deepseek-v4-flash。
RepoPilot 模型请求调用 1 个工具。
RepoPilot 调用工具：repo_list_tree。
...
RepoPilot 第 8 轮：请求模型 deepseek-v4-flash。
RepoPilot 模型请求调用 3 个工具。
RepoPilot 调用工具：repo_read_file。
RepoPilot 工具完成：repo_read_file（119 ms）。
RepoPilot 调用工具：repo_search_text。
RepoPilot 工具完成：repo_search_text（1510 ms）。
RepoPilot 调用工具：repo_search_text。
RepoPilot 工具完成：repo_search_text（1762 ms）。
RepoPilot 操作结束。
达到最大工具轮次限制：8

1. 这真的很蠢吧，这个 Agent 被你搞得完全没有自然语言能力，只会机械处理命令吗？我设想的本该是一个可以自然聊天的普通 Agent 附加上我们的那些额外功能啊？现在我说啥他都莫名其妙去一直工具调用，完全没输出了。是不是可以加一个意图识别？或者什么别的东西？你要针对这个改进点做一个严密详细的 Plan，如有问题向我提问。
2. 这个最大工具轮次限制，包括很多地方的超时限制，包括很多其他的这种参数，用户不能调整吗？我认为此项目的各种参数应该是高度可调节的。对于 CLI，使用命令调节，但其实 /help 提供的命令指南也有限。你后面应该考虑在 docs/ 下写一份 100% 全面、覆盖所有已实现命令的清单指南。至于在 WebUI 中，这些设置在一个单独的设置页面里面可调就好了。还是那句话，CLI 和 WebUI 的功能不能有任何出入。这些改参数的背后反映到软件里就是直接改配置文件就行。
```

```text
1. 我其实有在想，假如用户输入的 prompt 是这样：
/help 你还有什么其他功能吗？
这种命令 + 自然语言复合的形式，你会如何处理？我自己设想的是 / 开头的一律按指令处理，如果有误则提示用户有误。也可以调用 Agent 理解一下这行 prompt，然后告诉用户“我猜你可能是想输入 /help”或者“不可以复合”之类的？
2. 我们既然要开始为 Agent 增添普通聊天时的性格之类的，则 system_prompt.md 或者更多的预设定背景就需要引入或优化了，这点你要记住。
3. /help 看情况吧，也不用输出得太繁琐。我认为 /help 提供指令的简要查表，然后也可以引导用户去看那份 md。毕竟如果命令特别多，还有各种变形的话，一个 /help 输出好几页内容在命令行里，这也不是很方便查阅。
你的其他分析都没问题。再做一轮综合整合的 Plan。
```

```text
意图识别为啥要靠写死的关键词啊？我们这样不是相当于一直在亡羊补牢吗？测出来某个毛病→把这个词加进去，哪能这么开发呢？不能有一个 Agent 节点做意图识别的工作吗？这烧不了几毛钱 token 吧？那我的想法是：只有当用户输入以 / 开头时进入命令识别，靠硬编码来执行命令或者识别报错；其余一概先走到一个意图识别 Agent 节点上。不该这样吗？现在大部分 Agent 应用不是这么做的吗？
```

```text
对，这很有必要补充。比如说意图识别你一开始非要用硬编码搜索那几个关键词，然后我跟你说这块儿要拿 LLM 当节点来做。这种都是关键信息吧。
```

### Codex 协作结果摘要

- 这是开发中最关键的一次纠偏：最初 Agent 对普通问题也过度调用仓库工具，导致“你还能做什么”这类能力询问被错误路由成仓库分析。
- 修正后采用两层入口：以 `/` 开头的输入只走确定性命令解析；普通自然语言先进入 LLM Intent Router，再决定是普通回答、能力说明、配置说明、仓库分析还是任务简报。
- 这避免了靠关键词持续补丁式修复，也让 RepoPilot 从“一次性仓库扫描工具”更接近真正的多轮 Agent。

## 阶段 7：工程质量、开源维护与发布前复核

### 用户核心 Prompt 摘录

```text
我觉得还是要扣细节吧。你必须对这个项目（文档、配置、代码等各种文件内容）做一轮彻底的最终扫描、检测、优化，以确保没有各种各样的问题。我自己去文件里随便一看就是个问题（比如说你泄露我隐私什么的），这很难办啊。
这之后，我会去试着接 DeepSeek 的 API 并从 GitHub 拉取一个小体量规范仓库专门用于被扫描，以测试项目的可行性。
如果到这里都没问题，做一次 commit 并 push。
这之后我们再着手优化 CLI 的美观性并开发 WebUI。
```

```text
我注意到你文档写得不太行啊。比如说 CONTRIBUTING.md 这种，你没有从开发者的角度写，而是直接从我的角度写了。 
“拼写、链接、注释、轻量文档修正等 trivial change 可以直接提交到 main，但仍应保持提交内容聚焦。”是不是和我们刚才加的约束有冲突？结合我们完善的仓库约束，你要看看文档里是不是很多地方需要修改了。
“维护者可以 self-assign issue，并在 PR 中使用 Closes #<issue-number> 关联。”你把 self-assign 写进 CONTRIBUTING.md 是打算给谁看呢？
类似的问题说不定还有，我简单看一眼就发现这么多。之前让你优化文档，没想到优化得这么不彻底。说好的当成开源仓库维护，结果你只是把课程设计的思维去掉了，然后转向把文档都写给我看的风格了。咋这样呢？
再做一次全部文档的通扫。这个文档改动一会儿直接在 main 上做就行（只是图省事儿 不要当成典型操作）。
```

```text
我决定认真耕耘＆维护这个项目，而不仅仅止步于课程作业。所以从今往后在这个对话里对这个项目展开维护和开发，你就不用考虑课程作业的事儿了，而是严格按照开源社区的质量标准等规范来执行。

另，昨天的 0.1.0 版本是正确的，已经不用再撤 Tag 了。我觉得我们以后也尽量避免撤 Tag 这样的事情，大概开发一段时间然后定论之后打上 Tag 就不动了。接下来我们开始处理 0.1.1 的优化维护。
```

### Codex 协作结果摘要

- 项目从“课程实验产物”升级为按公开开源项目标准维护：README、CONTRIBUTING、SECURITY、CHANGELOG、Issue / PR 模板、CI、分支保护、Release Note 都进行了规范化。
- 文档语言和读者视角被重新校准：面向潜在用户和贡献者，而不是只写给作者本人或课程验收。
- 发布流程改为稳定 Tag，不轻易撤 Tag；后续改动通过 issue、分支、PR、CI、squash merge 和 milestone 管理。

## 阶段 8：运行时存储与清理能力

### 用户核心 Prompt 摘录

```text
目前，用户可以在任意路径执行 repopilot 命令，然后进去之后默认就是在执行命令的路径探测仓库，当然也支持更改。但这其实引出了一些问题：
2.1 用户在每个不同仓库都需要重新初始化，建立仓库级的 .repopilot 并填写 provider 和 api-key 等信息。整个 Agent 的配置文件也是仓库级的。
2.2 我们很难保证 .repopilot 在 git push 时被忽略。设想这样一个场景：我拉取某个仓库，使用 repopilot 分析理解，然后开始在仓库中工作。我最终还需要提交到别人的源仓库那里，所以 .repopilot 不可能写进人家的项目 .gitignore。但这又会导致我的 .repopilot 直接被上传（或者需要很费心地每次都从暂存中剔除出去），极易导致 api-key 等关键字段泄露。
```

```text
REPOPILOT_HOME 这种中央集成思路是对的，所以你要分清哪些配置是全局级的（比如 provider、api-key），哪些配置是项目级的（项目路径等）。另外，要提供一个清理选项，即如果用户决定不用 repopilot，删除的时候可以直接清理掉整个 REPOPILOT_HOME。我自己测试的时候就是这样，我会在某个新建文件夹里建一个 .venv 然后在 .venv 中通过 pip 安装 repopilot 进行测试。删除的时候我通常直接删掉整个新建文件夹，但这就不能清掉 REPOPILOT_HOME 这些外部配置项了。
```

```text
最后把这个做了吧，然后今天就可以收工了。
[Feature] Add runtime cleanup commands for REPOPILOT_HOME  #2
 ## 背景 / Problem 

如果 RepoPilot 引入 `REPOPILOT_HOME`，用户卸载或停止使用 RepoPilot 时，需要有明确方式清理运行时配置、API Key、repo profiles 和报告。

仅删除虚拟环境或安装目录不会自动删除 `REPOPILOT_HOME`。

## 目标 / Goal

提供安全、明确、可预览的清理命令，让用户知道 RepoPilot 在本机保存了哪些数据，并能一键清理。

## 方案草案 / Proposal

新增命令：

repopilot config home
repopilot config clean --dry-run
repopilot config clean
repopilot config clean --yes

行为：

- `home` 显示当前 `REPOPILOT_HOME`、配置文件、env 文件、repo profile 数量和报告目录。
- `clean --dry-run` 只列出将删除的内容，不实际删除。
- `clean` 需要二次确认。
- `clean --yes` 跳过确认，适合自动化测试。
- 删除前必须确认目标目录是 RepoPilot home，避免误删用户自定义目录。

## 验收标准 / Acceptance Criteria

- [ ] `repopilot config home` 能清楚显示当前运行时目录。
- [ ] `repopilot config clean --dry-run` 不删除文件。
- [ ] `repopilot config clean` 默认要求确认。
- [ ] `repopilot config clean --yes` 可用于测试。
- [ ] 清理逻辑拒绝删除非 RepoPilot home 目录。
- [ ] README 和 docs/configuration.md 说明卸载和清理方式。
```

### Codex 协作结果摘要

- 运行时配置从仓库内 `.repopilot` 调整为 `REPOPILOT_HOME`，降低用户在他人仓库贡献代码时误提交 API Key 和运行数据的风险。
- 区分全局配置和 repo profile：provider / API Key 属于全局运行时设置，仓库路径和报告属于特定 repo profile。
- 增加 `repopilot config home` 和 `repopilot config clean`，支持 dry-run、二次确认、`--yes` 自动确认和 marker 校验，避免误删非 RepoPilot home 目录。

## 阶段 9：反思素材：AI 协作中的问题与修正

### 用户核心 Prompt 摘录

```text
我目前看下来，我们的协作方式是这样：你写代码能力特别强，但是几乎不会提出实用的点子。每一个功能 / 实现 / 体验优化都是我提出来你才反应过来，就像刚刚的意图识别，我不说的话你就不知道拿 Agent 做，最后效果就不好。我很担心这个开发模式，因为这意味着此项目的能力边界完全取决于我的认知边界，而我实际上并不是资深 Agent 开发者。所以你不给一些启发 / 主动提建议是不行的。我现在去测试你之前的改动效果。在此过程中，你考不考虑充分参考现有的各个同领域开源项目 / 产品，看看我们的项目和业界常用方法有哪些出入？在这些方面有什么可以优化的地方？
2. 另外，也不要忘了代码、文档、配置项等本身的优化，包括你刚刚又做了那么多事情，有没有引入冗余代码？有没有引入错误？是否哪里写的不干净？是否看着像拼拼凑凑的代码而不是流畅的？之类的。这项检查也是必须要做的。
```

```text
你应该注意到我非常在意一致性（操作逻辑、代码、文档等各种地方）和简洁性（代码、文档、配置项等各种地方）。我目前经过自己手动测试，确认 CLI 已经没啥优化空间了。我希望你现在对整个代码仓库进行一次全量的扫描，这一步不要依赖任何你的已有记忆，必须去扫描读取，不遗漏任何地方，找出所有的问题、可优化的地方等，以确保最终代码、文档等质量极其过关，可以直接提交。
```

### Codex 协作结果摘要

- 反思重点不是“AI 一次生成了完整项目”，而是 AI 在多次迭代中会出现视角窄、实现导向过强、默认方案不够产品化的问题。
- 关键修正方式是：用明确的验收标准、真实手动测试、反例日志、开源项目规范和一致性检查不断约束 AI 输出。
- 最终 RepoPilot 的质量来自“用户提出问题和标准 + Codex 快速实现与复核”的协作闭环，而不是单轮生成。