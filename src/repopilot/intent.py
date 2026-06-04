"""Intent routing for RepoPilot chat input."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import get_close_matches
from typing import Literal

from pydantic import BaseModel, Field


IntentName = Literal[
    "meta_help",
    "casual_chat",
    "explain_context",
    "repo_overview",
    "repo_runbook",
    "repo_module_map",
    "repo_task_brief",
    "repo_deep_scan",
    "config_request",
    "ambiguous",
]
IntentMode = Literal["overview", "runbook", "module-map", "task-brief", "deep-scan"]


@dataclass(frozen=True)
class Intent:
    name: IntentName
    confidence: float
    reason: str


class IntentDecision(BaseModel):
    intent: IntentName
    confidence: float = Field(ge=0, le=1)
    needs_tools: bool
    mode: IntentMode | None = None
    task: str | None = None
    reply_strategy: str = ""
    clarifying_question: str | None = None
    reason: str = ""
    source: Literal["llm", "rules", "fallback"] = "llm"


COMMAND_SPECS: dict[str, dict[str, object]] = {
    "/help": {"args": "optional_group", "usage": "/help [chat|config|mcp|reports]"},
    "/overview": {"args": "none", "usage": "/overview"},
    "/runbook": {"args": "none", "usage": "/runbook"},
    "/module-map": {"args": "none", "usage": "/module-map"},
    "/task-brief": {"args": "required", "usage": "/task-brief <task>"},
    "/deep-scan": {"args": "none", "usage": "/deep-scan"},
    "/mcp": {"args": "optional_choice", "choices": {"on", "off"}, "usage": "/mcp [on|off]"},
    "/tools": {"args": "none", "usage": "/tools"},
    "/sources": {"args": "none", "usage": "/sources"},
    "/artifacts": {"args": "none", "usage": "/artifacts"},
    "/save": {"args": "optional_value", "usage": "/save [filename.md]"},
    "/config": {"args": "none", "usage": "/config"},
    "/settings": {"args": "settings", "usage": "/settings [get|set|reset] ..."},
    "/provider": {"args": "none", "usage": "/provider"},
    "/api-key": {"args": "none", "usage": "/api-key"},
    "/status": {"args": "none", "usage": "/status"},
    "/setup": {"args": "none", "usage": "/setup"},
    "/clear": {"args": "none", "usage": "/clear"},
    "/exit": {"args": "none", "usage": "/exit"},
    "/quit": {"args": "none", "usage": "/quit"},
}

HELP_GROUPS = {"chat", "config", "mcp", "reports"}


def validate_slash_command(command_line: str) -> str | None:
    """Return a user-facing validation error for a slash command, if any."""

    name, _, rest = command_line.strip().partition(" ")
    spec = COMMAND_SPECS.get(name)
    if spec is None:
        suggestion = get_close_matches(name, COMMAND_SPECS.keys(), n=1)
        if suggestion:
            return f"未知命令：{name}。你可能想输入 `{suggestion[0]}`。"
        return f"未知命令：{name}。输入 `/help` 查看命令。"

    arg_kind = spec["args"]
    rest = rest.strip()
    usage = str(spec["usage"])
    if arg_kind == "none" and rest:
        return f"`{name}` 不接受参数。用法：`{usage}`。如果想自然提问，请直接输入问题，不要以 `/` 开头。"
    if arg_kind == "required" and not rest:
        return f"`{name}` 需要参数。用法：`{usage}`。"
    if arg_kind == "optional_choice" and rest and rest not in spec.get("choices", set()):
        return f"`{name}` 的参数无效。用法：`{usage}`。"
    if arg_kind == "optional_group" and rest and rest not in HELP_GROUPS:
        return f"`{name}` 只接受这些分组：chat、config、mcp、reports。自然问题请直接输入，不要写在 `/help` 后面。"
    return None


def decision_from_rule(intent: Intent, message: str) -> IntentDecision:
    mode_by_intent: dict[IntentName, IntentMode] = {
        "repo_overview": "overview",
        "repo_runbook": "runbook",
        "repo_module_map": "module-map",
        "repo_task_brief": "task-brief",
        "repo_deep_scan": "deep-scan",
    }
    mode = mode_by_intent.get(intent.name)
    return IntentDecision(
        intent=intent.name,
        confidence=intent.confidence,
        needs_tools=mode is not None,
        mode=mode,
        task=message if mode == "task-brief" else None,
        reply_strategy="rule_fallback",
        clarifying_question="请更明确地描述你想分析仓库、配置工具，还是解释已有报告。" if intent.name == "ambiguous" else None,
        reason=intent.reason,
        source="rules",
    )


def classify_intent_by_rules(message: str, has_context: bool) -> Intent:
    """Fallback rule classifier for natural-language chat."""

    text = message.strip()
    lowered = text.lower()
    if not text:
        return Intent("ambiguous", 0.0, "空输入")

    if any(word in text for word in ("你还能做什么", "还能做什么", "你能做什么", "做什么", "有什么功能", "其他功能", "怎么用", "如何使用", "帮助")) or any(
        word in lowered for word in ("what can you do", "help", "usage")
    ):
        return Intent("meta_help", 0.95, "用户询问能力或用法")

    if any(word in text for word in ("配置", "设置", "参数", "API Key", "供应商", "模型", "MCP", "联网", "超时", "轮次")):
        return Intent("config_request", 0.86, "用户询问配置或运行参数")

    if has_context and any(word in text for word in ("解释", "说明", "刚才", "上一轮", "这份报告", "没懂", "为什么", "什么意思")):
        return Intent("explain_context", 0.9, "用户要求解释已有上下文")

    if any(word in text for word in ("运行", "测试", "构建", "启动", "安装", "依赖")) or any(
        word in lowered for word in ("run", "test", "build", "start", "install")
    ):
        return Intent("repo_runbook", 0.82, "用户询问运行构建线索")

    if any(word in text for word in ("模块", "目录", "结构", "入口", "架构")) or any(
        word in lowered for word in ("module", "map", "entry", "architecture")
    ):
        return Intent("repo_module_map", 0.82, "用户询问模块结构")

    if any(word in text for word in ("深入扫描", "完整入职", "入职包", "全面分析", "深度分析")) or any(
        word in lowered for word in ("deep scan", "deep-scan", "onboarding")
    ):
        return Intent("repo_deep_scan", 0.82, "用户要求完整仓库入职包")

    if any(word in text for word in ("分析仓库", "分析这个仓库", "看看仓库", "仓库概览", "整体介绍", "项目是干嘛")):
        return Intent("repo_overview", 0.82, "用户要求整体仓库分析")

    if any(word in text for word in ("在哪里", "找", "定位", "修改", "实现", "功能", "流程", "bug", "修复")) or any(
        word in lowered for word in ("where", "find", "locate", "fix", "implement", "bug")
    ):
        return Intent("repo_task_brief", 0.72, "用户围绕任务定位代码")

    if has_context:
        return Intent("explain_context", 0.55, "已有上下文下的普通追问")

    return Intent("casual_chat", 0.5, "普通对话")
