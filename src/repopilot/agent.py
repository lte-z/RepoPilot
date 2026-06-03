"""Agent orchestration for RepoPilot."""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI

from .config import AppConfig, load_config
from .permissions import PathGuard
from .tools.repository import (
    DetectStackInput,
    GitSummaryInput,
    ListTreeInput,
    ReadFileInput,
    SearchTextInput,
    repo_detect_stack,
    repo_git_summary,
    repo_list_tree,
    repo_read_file,
    repo_search_text,
)


Mode = Literal["overview", "runbook", "module-map", "task-brief"]
MODES: tuple[Mode, ...] = ("overview", "runbook", "module-map", "task-brief")


MODE_INSTRUCTIONS: dict[Mode, str] = {
    "overview": "生成仓库概览：用途、技术栈、关键目录、重要文件。",
    "runbook": "推断运行手册：安装、启动、测试、构建方式和证据来源。",
    "module-map": "梳理模块地图：目录职责、入口文件、核心模块关系。",
    "task-brief": "生成任务简报：围绕用户任务搜索相关文件，给阅读顺序和风险点。",
}


def validate_mode(mode: str) -> Mode:
    if mode not in MODES:
        allowed = ", ".join(MODES)
        raise ValueError(f"未知分析模式：{mode}；可选模式：{allowed}")
    return mode  # type: ignore[return-value]


@dataclass
class ToolCallLog:
    name: str
    arguments: dict[str, Any]
    duration_ms: int
    preview: str


@dataclass
class AnalysisResult:
    mode: Mode
    repo_path: str
    markdown: str
    tool_calls: list[ToolCallLog] = field(default_factory=list)
    offline: bool = False


def _load_system_prompt() -> str:
    path = Path(__file__).resolve().parent / "prompts" / "system_prompt.md"
    return path.read_text(encoding="utf-8")


def _preview(text: str, limit: int = 240) -> str:
    compact = " ".join(text.split())
    return compact[:limit] + ("..." if len(compact) > limit else "")


def _tool_result_text(result: Any) -> str:
    content = getattr(result, "content", None)
    if not content:
        return str(result)
    chunks: list[str] = []
    for item in content:
        text = getattr(item, "text", None)
        if text is not None:
            chunks.append(text)
    return "\n".join(chunks) if chunks else str(result)


def _mcp_tool_to_openai(tool: Any) -> dict[str, Any]:
    schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None) or {}
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or f"RepoPilot tool {tool.name}",
            "parameters": schema,
        },
    }


def _build_user_prompt(mode: Mode, repo_path: str, task: str | None) -> str:
    task_text = f"\n用户任务：{task}" if task else ""
    return (
        f"分析模式：{mode}\n"
        f"模式要求：{MODE_INSTRUCTIONS[mode]}\n"
        f"仓库路径：{repo_path}{task_text}\n\n"
        "请自主调用可用工具收集证据，然后输出中文 Markdown。"
    )


def _task_search_queries(task: str) -> list[str]:
    normalized = task.strip()
    queries: list[str] = []
    if normalized:
        queries.append(normalized)
    words = re.findall(r"[A-Za-z0-9_./-]{2,}|[\u4e00-\u9fff]{2,}", normalized)
    for word in words:
        if word not in queries:
            queries.append(word)
        if re.fullmatch(r"[\u4e00-\u9fff]{5,}", word):
            for index in range(0, len(word) - 1, 2):
                chunk = word[index : index + 2]
                if chunk not in queries:
                    queries.append(chunk)
        if len(queries) >= 4:
            break
    return queries[:4]


def _offline_report(mode: Mode, repo_path: str, task: str | None, config: AppConfig) -> AnalysisResult:
    guard = PathGuard(config, repo_path)
    logs: list[ToolCallLog] = []

    def call(name: str, fn: Any, params: Any) -> str:
        start = time.perf_counter()
        text = fn(params, config)
        logs.append(
            ToolCallLog(
                name=name,
                arguments=params.model_dump(),
                duration_ms=int((time.perf_counter() - start) * 1000),
                preview=_preview(text),
            )
        )
        return text

    tree = call("repo_list_tree", repo_list_tree, ListTreeInput(repo_path=str(guard.session_repo), max_depth=2))
    stack = call("repo_detect_stack", repo_detect_stack, DetectStackInput(repo_path=str(guard.session_repo)))
    git = call("repo_git_summary", repo_git_summary, GitSummaryInput(repo_path=str(guard.session_repo)))
    searches: list[str] = []
    if task:
        for query in _task_search_queries(task):
            searches.append(
                call(
                    "repo_search_text",
                    repo_search_text,
                    SearchTextInput(repo_path=str(guard.session_repo), query=query, max_results=10),
                )
            )

    markdown = [
        "## 结论",
        f"RepoPilot 已在离线模式下完成 `{mode}` 侦察。该模式不调用 LLM，只整合本地工具结果，适合验证工具链和截图准备。",
        "",
        "## 证据",
        stack,
        "",
        tree,
        "",
        git,
    ]
    if searches:
        markdown.extend(["", "## 任务相关搜索"])
        for search in searches:
            markdown.extend(["", search])
    markdown.extend(
        [
            "",
            "## 建议下一步",
            "- 配置 `LLM_API_KEY` 后运行非离线模式，获取由模型综合工具证据后的完整简报。",
            "- 若要分析外部仓库，请确保仓库路径位于 `readable_roots` 白名单下。",
        ]
    )
    return AnalysisResult(mode=mode, repo_path=str(guard.session_repo), markdown="\n".join(markdown), tool_calls=logs, offline=True)


async def analyze_repository(
    mode: str,
    repo_path: str,
    task: str | None = None,
    *,
    config_path: str | Path | None = None,
    offline: bool = False,
) -> AnalysisResult:
    """Run RepoPilot analysis through MCP tool calls and an OpenAI-compatible model."""

    selected_mode = validate_mode(mode)
    if selected_mode == "task-brief" and not task:
        raise ValueError("task-brief 模式需要提供任务文本。")
    config = load_config(config_path)
    guard = PathGuard(config, repo_path)
    if offline:
        return _offline_report(selected_mode, str(guard.session_repo), task, config)
    if not config.llm.api_key:
        raise RuntimeError("缺少 LLM_API_KEY。请配置 .env，或使用 --offline 验证本地工具链。")

    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "repopilot.mcp_server"],
        cwd=str(config.project_root),
    )
    client = AsyncOpenAI(api_key=config.llm.api_key, base_url=config.llm.base_url)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _load_system_prompt()},
        {"role": "user", "content": _build_user_prompt(selected_mode, str(guard.session_repo), task)},
    ]
    logs: list[ToolCallLog] = []

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            openai_tools = [_mcp_tool_to_openai(tool) for tool in listed.tools]

            for _ in range(config.limits.max_tool_rounds):
                response = await client.chat.completions.create(
                    model=config.llm.model,
                    messages=messages,
                    tools=openai_tools,
                    tool_choice="auto",
                )
                message = response.choices[0].message
                messages.append(message.model_dump(exclude_none=True))
                tool_calls = message.tool_calls or []
                if not tool_calls:
                    return AnalysisResult(
                        mode=selected_mode,
                        repo_path=str(guard.session_repo),
                        markdown=message.content or "",
                        tool_calls=logs,
                    )
                for call in tool_calls:
                    args = json.loads(call.function.arguments or "{}")
                    args.setdefault("repo_path", str(guard.session_repo))
                    start = time.perf_counter()
                    result = await session.call_tool(call.function.name, args)
                    text = _tool_result_text(result)
                    logs.append(
                        ToolCallLog(
                            name=call.function.name,
                            arguments=args,
                            duration_ms=int((time.perf_counter() - start) * 1000),
                            preview=_preview(text),
                        )
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": text,
                        }
                    )

    raise RuntimeError(f"达到最大工具轮次限制：{config.limits.max_tool_rounds}")


def run_analysis(*args: Any, **kwargs: Any) -> AnalysisResult:
    return asyncio.run(analyze_repository(*args, **kwargs))
