"""Multi-turn session state built on top of RepoPilot analysis modes."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal, cast

from .agent import AnalysisResult, Mode, TokenUsage, run_analysis, run_plain_chat
from .config import load_config
from .intent import IntentDecision
from .intent_agent import run_intent_router
from .permissions import PathGuard
from .tools.repository import SaveReportInput, repo_save_report


Role = Literal["user", "assistant", "system"]
ProgressCallback = Callable[[str], None]


@dataclass
class SessionMessage:
    role: Role
    content: str
    created_at: float = field(default_factory=time.time)


@dataclass
class ToolEvent:
    name: str
    duration_ms: int
    preview: str


@dataclass
class Artifact:
    id: str
    title: str
    mode: str
    markdown: str
    saved_path: str | None = None
    token_usage: TokenUsage | None = None
    created_at: float = field(default_factory=time.time)


@dataclass
class SourceReference:
    label: str
    detail: str


@dataclass
class McpStatus:
    connected: bool
    transport: str
    tools: list[str]
    network_enabled: bool


@dataclass
class SessionState:
    session_id: str
    repo_path: str
    messages: list[SessionMessage] = field(default_factory=list)
    tool_events: list[ToolEvent] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)


def _title_for_mode(mode: str, repo_path: str) -> str:
    repo_name = Path(repo_path).name
    labels = {
        "overview": "仓库概览",
        "runbook": "运行手册",
        "module-map": "模块地图",
        "task-brief": "任务简报",
        "deep-scan": "仓库入职包",
    }
    return f"{repo_name} - {labels.get(mode, mode)}"


def _normalize_report_markdown(title: str, markdown: str) -> str:
    """Turn a chat artifact into a standalone Markdown report."""

    text = markdown.strip()
    lines = text.splitlines()
    while lines and lines[0].strip() in {"---", "***", "___"}:
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
    if not lines:
        return f"# {title}\n"

    has_h1 = any(line.startswith("# ") for line in lines)
    if has_h1:
        return "\n".join(lines).strip() + "\n"

    first_heading_index = next((index for index, line in enumerate(lines) if line.startswith("## ")), None)
    first_heading = lines[first_heading_index][3:].strip() if first_heading_index is not None else ""
    fixed_sections = {"结论", "证据", "建议下一步"}
    if first_heading and first_heading not in fixed_sections:
        promoted: list[str] = []
        for line in lines:
            if line.startswith("##"):
                promoted.append(line[1:])
            else:
                promoted.append(line)
        return "\n".join(promoted).strip() + "\n"

    return f"# {title}\n\n" + "\n".join(lines).strip() + "\n"


def _usage_from_decision(decision: IntentDecision) -> TokenUsage | None:
    usage = TokenUsage(
        prompt_tokens=decision.prompt_tokens,
        completion_tokens=decision.completion_tokens,
        total_tokens=decision.total_tokens,
    )
    return usage if usage.has_tokens else None


def _merge_usage(*items: TokenUsage | None) -> TokenUsage | None:
    merged = TokenUsage()
    for item in items:
        merged.merge(item)
    return merged if merged.has_tokens else None


class ChatSession:
    """A lightweight conversation wrapper around RepoPilot quick actions."""

    def __init__(
        self,
        repo_path: str,
        *,
        config_path: str | Path | None = None,
        offline: bool = False,
        session_id: str | None = None,
    ):
        self.config_path = config_path
        self.offline = offline
        self.config = load_config(config_path)
        guard = PathGuard(self.config, repo_path)
        self.state = SessionState(session_id=session_id or uuid.uuid4().hex[:12], repo_path=str(guard.session_repo))

    def _context_snippet(self) -> str:
        if not self.state.artifacts:
            return ""
        chunks = ["已有会话上下文："]
        max_items = max(1, self.config.limits.max_context_artifacts)
        for artifact in self.state.artifacts[-max_items:]:
            excerpt = " ".join(artifact.markdown.split())[:1200]
            chunks.append(f"- {artifact.title}：{excerpt}")
        return "\n".join(chunks)

    def _record_result(self, result: AnalysisResult, title: str | None = None) -> Artifact:
        self.state.tool_events.extend(
            ToolEvent(name=call.name, duration_ms=call.duration_ms, preview=call.preview)
            for call in result.tool_calls
        )
        artifact = Artifact(
            id=uuid.uuid4().hex[:10],
            title=title or _title_for_mode(result.mode, result.repo_path),
            mode=result.mode,
            markdown=result.markdown,
            token_usage=result.token_usage,
        )
        self.state.artifacts.append(artifact)
        self.state.messages.append(SessionMessage(role="assistant", content=result.markdown))
        return artifact

    def _record_chat_reply(self, title: str, markdown: str, token_usage: TokenUsage | None = None) -> Artifact:
        artifact = Artifact(
            id=uuid.uuid4().hex[:10],
            title=title,
            mode="chat",
            markdown=markdown.strip() + "\n",
            token_usage=token_usage,
        )
        self.state.artifacts.append(artifact)
        self.state.messages.append(SessionMessage(role="assistant", content=artifact.markdown))
        return artifact

    def classify(self, message: str) -> IntentDecision:
        return run_intent_router(
            message,
            repo_path=self.state.repo_path,
            context=self._context_snippet(),
            has_context=bool(self.state.artifacts),
            config_path=self.config_path,
            offline=self.offline,
        )

    def _capability_reply(self) -> str:
        return "\n".join(
            [
                "## 我能做什么",
                "",
                "我可以像普通助手一样解释当前会话里的内容，也可以在你明确需要仓库证据时调用 MCP 工具。",
                "",
                "### 常用能力",
                "",
                "- 生成仓库概览：`/overview`，或直接说“分析这个仓库”。",
                "- 推断运行手册：`/runbook`，或询问安装、启动、测试、构建方式。",
                "- 梳理模块地图：`/module-map`，或询问目录结构、入口文件、核心模块。",
                "- 围绕任务定位文件：`/task-brief <任务>`，或直接描述你要修什么、找什么。",
                "- 生成完整入职包：`/deep-scan`，用于更系统地理解陌生仓库。",
                "- 解释已有报告：在生成报告后直接追问“这段是什么意思”“为什么先看这个文件”。",
                "- 管理配置：`/provider`、`/api-key`、`/mcp`、`/settings`。",
                "",
                "### 输入规则",
                "",
                "- 以 `/` 开头的是命令，只走命令解析器。",
                "- 普通自然语言会先做意图识别，只有需要仓库证据时才调用工具。",
                "- 输入 `/help` 查看简表，完整命令见 `docs/cli-reference.md`。",
            ]
        )

    def _config_reply(self) -> str:
        config = load_config(self.config_path)
        return "\n".join(
            [
                "## 配置入口",
                "",
                "当前会话可以通过命令修改本地 `.repopilot/` 配置，不需要手动编辑文件。",
                "",
                "### 常用命令",
                "",
                "- `/provider`：选择 LLM 供应商、Base URL 和模型。",
                "- `/api-key`：保存或更新 API Key。",
                "- `/mcp`、`/mcp on`、`/mcp off`：查看或切换联网 MCP 工具。",
                "- `/settings`：查看可调配置。",
                "- `/settings get limits.max_tool_rounds`：读取单个配置。",
                "- `/settings set limits.max_tool_rounds 12`：修改单个配置。",
                "",
                "### 当前关键状态",
                "",
                f"- 模型：`{config.llm.model or '<empty>'}`",
                f"- HTTP Fetch：`{'on' if config.network.allow_http_fetch else 'off'}`",
                f"- 最大工具轮次：`{config.limits.max_tool_rounds}`",
                f"- LLM 超时：`{config.limits.llm_timeout_seconds}` 秒",
                f"- 工具超时：`{config.limits.tool_timeout_seconds}` 秒",
            ]
        )

    def _explain_context_reply(self, message: str) -> str:
        if not self.state.artifacts:
            return "## 还没有可解释的上下文\n\n当前会话还没有生成报告。你可以先运行 `/overview`，或直接说“分析这个仓库”。"
        latest = self.state.artifacts[-1]
        excerpt = " ".join(latest.markdown.split())[:1400]
        return "\n".join(
            [
                "## 基于当前上下文的解释",
                "",
                f"你刚才的问题是：{message}",
                "",
                f"我目前能参考的最近一份报告是 `{latest.title}`。它的核心内容可以压缩成：",
                "",
                excerpt,
                "",
                "如果你想让我重新读取仓库证据，请明确说要分析哪一块，或使用 `/task-brief <任务>`。",
            ]
        )

    def _plain_chat_reply(self, message: str, fallback: str) -> tuple[str, TokenUsage | None]:
        try:
            reply = run_plain_chat(
                message,
                context=self._context_snippet(),
                config_path=self.config_path,
                offline=self.offline,
            )
        except Exception:
            # Plain chat is optional; keep the session usable if the no-tools LLM turn fails.
            reply = None
        if reply and reply.markdown.strip():
            return reply.markdown.strip(), reply.token_usage
        return fallback, None

    def run_quick_action(self, mode: Mode, task: str | None = None, progress: ProgressCallback | None = None) -> Artifact:
        self.state.messages.append(SessionMessage(role="user", content=f"/{mode}" + (f" {task}" if task else "")))
        result = run_analysis(
            mode,
            self.state.repo_path,
            task,
            config_path=self.config_path,
            offline=self.offline,
            progress=progress,
        )
        return self._record_result(result)

    def send_message(self, message: str, progress: ProgressCallback | None = None) -> Artifact:
        self.state.messages.append(SessionMessage(role="user", content=message))
        if progress:
            progress("正在识别意图。")
        decision = self.classify(message)
        intent_usage = _usage_from_decision(decision)
        if progress:
            progress(f"意图：{decision.intent}（{decision.source}，{decision.reason}）。")

        if decision.intent == "meta_help":
            return self._record_chat_reply("能力说明", self._capability_reply(), intent_usage)
        if decision.intent == "config_request":
            return self._record_chat_reply("配置说明", self._config_reply(), intent_usage)
        if decision.intent == "ambiguous":
            question = decision.clarifying_question or "我不确定你想聊天、配置，还是分析仓库。可以换一种更明确的说法吗？"
            return self._record_chat_reply("澄清", f"## 我需要确认一下\n\n{question}", intent_usage)
        if decision.intent == "casual_chat":
            fallback = (
                "## 我在\n\n"
                "我可以普通聊天，但我的专长是帮你理解当前选择的代码仓库。"
                "如果你想让我读取仓库，请说“分析这个仓库”“生成运行手册”，或使用 `/overview`、`/task-brief <任务>`。"
            )
            reply, token_usage = self._plain_chat_reply(message, fallback)
            return self._record_chat_reply("对话", reply, _merge_usage(intent_usage, token_usage))
        if decision.intent == "explain_context":
            fallback = self._explain_context_reply(message)
            reply, token_usage = self._plain_chat_reply(message, fallback)
            return self._record_chat_reply("上下文解释", reply, _merge_usage(intent_usage, token_usage))

        if not decision.needs_tools or decision.mode is None:
            return self._record_chat_reply(
                "澄清",
                "## 我需要确认一下\n\n意图识别没有给出可执行的仓库分析模式。你可以使用 `/overview`、`/runbook` 或 `/task-brief <任务>`。",
                intent_usage,
            )

        mode_by_intent: dict[str, Mode] = {
            "repo_overview": "overview",
            "repo_runbook": "runbook",
            "repo_module_map": "module-map",
            "repo_task_brief": "task-brief",
            "repo_deep_scan": "deep-scan",
        }
        mode = mode_by_intent.get(decision.intent, cast(Mode, decision.mode))
        context = self._context_snippet()
        selected_task = decision.task or message
        task = selected_task if not context else f"{selected_task}\n\n{context}"
        result = run_analysis(
            mode,
            self.state.repo_path,
            task if mode == "task-brief" else None,
            config_path=self.config_path,
            offline=self.offline,
            progress=progress,
        )
        result.token_usage = _merge_usage(intent_usage, result.token_usage)
        return self._record_result(result)

    def save_artifact(self, artifact_id: str | None = None, filename: str | None = None) -> str:
        if not self.state.artifacts:
            raise ValueError("当前会话还没有可保存的报告。")
        artifact = self.state.artifacts[-1] if artifact_id is None else next(
            (item for item in self.state.artifacts if item.id == artifact_id),
            None,
        )
        if artifact is None:
            raise ValueError(f"未找到 artifact：{artifact_id}")
        safe_name = filename or f"{Path(self.state.repo_path).name}-{artifact.mode}-{artifact.id}.md"
        content = _normalize_report_markdown(artifact.title, artifact.markdown)
        text = repo_save_report(SaveReportInput(filename=safe_name, content=content), load_config(self.config_path))
        artifact.saved_path = text
        return text

    def get_sources(self) -> list[SourceReference]:
        sources: list[SourceReference] = []
        for event in self.state.tool_events:
            sources.append(SourceReference(label=event.name, detail=event.preview))
        return sources

    def get_mcp_status(self) -> McpStatus:
        config = load_config(self.config_path)
        tools = [
            "repo_list_tree",
            "repo_read_file",
            "repo_search_text",
            "repo_detect_stack",
            "repo_git_summary",
            "repo_symbol_map",
            "repo_save_report",
        ]
        if config.network.allow_http_fetch:
            tools.append("web_fetch_url")
        return McpStatus(
            connected=True,
            transport="stdio",
            tools=tools,
            network_enabled=config.network.allow_http_fetch,
        )

    def clear(self) -> None:
        self.state.messages.clear()
        self.state.tool_events.clear()
        self.state.artifacts.clear()
