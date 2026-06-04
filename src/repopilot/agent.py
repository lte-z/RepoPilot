"""Agent orchestration for RepoPilot."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, cast

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
    SymbolMapInput,
    repo_detect_stack,
    repo_git_summary,
    repo_list_tree,
    repo_read_file,
    repo_search_text,
    repo_symbol_map,
)


Mode = Literal["overview", "runbook", "module-map", "task-brief", "deep-scan"]
MODES: tuple[Mode, ...] = ("overview", "runbook", "module-map", "task-brief", "deep-scan")


MODE_INSTRUCTIONS: dict[Mode, str] = {
    "overview": "生成仓库概览：用途、技术栈、关键目录、重要文件。",
    "runbook": "推断运行手册：安装、启动、测试、构建方式和证据来源。",
    "module-map": "梳理模块地图：目录职责、入口文件、核心模块关系。",
    "task-brief": "生成任务简报：围绕用户任务搜索相关文件，给阅读顺序和风险点。",
    "deep-scan": "生成仓库入职包：定位、技术栈、模块地图、入口、运行线索、符号地图、风险和阅读路径。",
}
ProgressCallback = Callable[[str], None]


def validate_mode(mode: str) -> Mode:
    if mode not in MODES:
        allowed = ", ".join(MODES)
        raise ValueError(f"未知分析模式：{mode}；可选模式：{allowed}")
    return cast(Mode, mode)


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


def _load_chat_prompt() -> str:
    path = Path(__file__).resolve().parent / "prompts" / "chat_prompt.md"
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


def _mcp_server_environment(config: AppConfig) -> dict[str, str]:
    """Build the environment inherited by the local MCP subprocess."""

    env = os.environ.copy()
    env["REPOPILOT_CONFIG"] = str(config.config_path)
    env["REPOPILOT_PROJECT_ROOT"] = str(config.project_root)
    return env


def _emit(progress: ProgressCallback | None, message: str) -> None:
    if progress:
        progress(message)


async def _with_timeout(awaitable: Any, timeout: float, label: str) -> Any:
    try:
        return await asyncio.wait_for(awaitable, timeout=timeout)
    except TimeoutError as exc:
        raise TimeoutError(f"{label} 超时（{timeout:g} 秒）。") from exc


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


def _mode_model(config: AppConfig, mode: Mode) -> str:
    mode_settings = config.modes.get(mode)
    if mode_settings and mode_settings.model:
        return mode_settings.model
    return config.llm.model


def _mode_tool_rounds(config: AppConfig, mode: Mode) -> int:
    mode_settings = config.modes.get(mode)
    if mode_settings and mode_settings.max_tool_rounds is not None:
        return mode_settings.max_tool_rounds
    return config.limits.max_tool_rounds


def _mode_enabled_tools(config: AppConfig, mode: Mode) -> set[str] | None:
    mode_settings = config.modes.get(mode)
    if mode_settings and mode_settings.enabled_tools:
        return set(mode_settings.enabled_tools)
    return None


def _tool_allowed_for_mode(config: AppConfig, mode: Mode, tool_name: str) -> bool:
    enabled_tools = _mode_enabled_tools(config, mode)
    if enabled_tools is not None and tool_name not in enabled_tools:
        return False
    if tool_name == "web_fetch_url" and not config.network.allow_http_fetch:
        return False
    return True


def _build_user_prompt(mode: Mode, repo_path: str, task: str | None) -> str:
    task_text = f"\n用户任务：{task}" if task else ""
    return (
        f"分析模式：{mode}\n"
        f"模式要求：{MODE_INSTRUCTIONS[mode]}\n"
        f"仓库路径：{repo_path}{task_text}\n\n"
        "请自主调用可用工具收集证据，然后输出中文 Markdown。"
    )


def _tool_signature(name: str, args: dict[str, Any]) -> str:
    return json.dumps({"name": name, "arguments": args}, ensure_ascii=False, sort_keys=True)


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

    tree_depth = 3 if mode == "deep-scan" else 2
    tree = call("repo_list_tree", repo_list_tree, ListTreeInput(repo_path=str(guard.session_repo), max_depth=tree_depth))
    stack = call("repo_detect_stack", repo_detect_stack, DetectStackInput(repo_path=str(guard.session_repo)))
    git = call("repo_git_summary", repo_git_summary, GitSummaryInput(repo_path=str(guard.session_repo)))
    symbol_map = ""
    if mode in {"module-map", "task-brief", "deep-scan"}:
        symbol_map = call("repo_symbol_map", repo_symbol_map, SymbolMapInput(repo_path=str(guard.session_repo)))
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
    if symbol_map:
        markdown.extend(["", "## 符号地图", symbol_map])
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
    progress: ProgressCallback | None = None,
) -> AnalysisResult:
    """Run RepoPilot analysis through MCP tool calls and an OpenAI-compatible model."""

    selected_mode = validate_mode(mode)
    if selected_mode == "task-brief" and not task:
        raise ValueError("task-brief 模式需要提供任务文本。")
    config = load_config(config_path)
    guard = PathGuard(config, repo_path)
    if offline:
        _emit(progress, "使用离线模式调用本地工具。")
        return _offline_report(selected_mode, str(guard.session_repo), task, config)
    if not config.llm.api_key:
        raise RuntimeError("缺少 LLM_API_KEY。请运行 repopilot config set-api-key，或使用 --offline 验证本地工具链。")
    if not config.llm.base_url or not config.llm.model:
        raise RuntimeError("缺少 LLM 供应商配置。请运行 repopilot config set-provider，或使用 --offline 验证本地工具链。")

    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "repopilot.mcp_server"],
        env=_mcp_server_environment(config),
        cwd=str(config.project_root),
    )
    selected_model = _mode_model(config, selected_mode)
    max_tool_rounds = _mode_tool_rounds(config, selected_mode)
    client = AsyncOpenAI(api_key=config.llm.api_key, base_url=config.llm.base_url, timeout=config.limits.llm_timeout_seconds)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _load_system_prompt()},
        {"role": "user", "content": _build_user_prompt(selected_mode, str(guard.session_repo), task)},
    ]
    logs: list[ToolCallLog] = []
    repeated_calls: dict[str, int] = {}

    try:
        _emit(progress, "启动本地 MCP server。")
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await _with_timeout(session.initialize(), 30, "MCP 初始化")
                _emit(progress, "MCP server 已连接，正在读取工具列表。")
                listed = await _with_timeout(session.list_tools(), 30, "读取 MCP 工具列表")
                filtered_tools = [tool for tool in listed.tools if _tool_allowed_for_mode(config, selected_mode, tool.name)]
                openai_tools = [_mcp_tool_to_openai(tool) for tool in filtered_tools]
                _emit(progress, f"已加载 {len(openai_tools)} 个 MCP 工具。")

                for round_index in range(max_tool_rounds):
                    _emit(progress, f"第 {round_index + 1} 轮：请求模型 {selected_model}。")
                    response = await _with_timeout(
                        client.chat.completions.create(
                            model=selected_model,
                            messages=messages,
                            tools=openai_tools,
                            tool_choice="auto",
                        ),
                        config.limits.llm_timeout_seconds,
                        "LLM 请求",
                    )
                    message = response.choices[0].message
                    messages.append(message.model_dump(exclude_none=True))
                    tool_calls = message.tool_calls or []
                    if not tool_calls:
                        _emit(progress, "模型已返回最终报告。")
                        return AnalysisResult(
                            mode=selected_mode,
                            repo_path=str(guard.session_repo),
                            markdown=message.content or "",
                            tool_calls=logs,
                        )
                    _emit(progress, f"模型请求调用 {len(tool_calls)} 个工具。")
                    for call in tool_calls:
                        args = json.loads(call.function.arguments or "{}")
                        args.setdefault("repo_path", str(guard.session_repo))
                        signature = _tool_signature(call.function.name, args)
                        repeated_calls[signature] = repeated_calls.get(signature, 0) + 1
                        if repeated_calls[signature] > config.limits.max_repeated_tool_calls:
                            text = (
                                f"重复工具调用已跳过：{call.function.name}。"
                                "请基于已有工具结果继续分析，不要重复读取相同参数。"
                            )
                            _emit(progress, f"跳过重复工具调用：{call.function.name}。")
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": call.id,
                                    "content": text,
                                }
                            )
                            continue
                        start = time.perf_counter()
                        _emit(progress, f"调用工具：{call.function.name}。")
                        result = await _with_timeout(
                            session.call_tool(call.function.name, args),
                            config.limits.tool_timeout_seconds,
                            f"工具 {call.function.name}",
                        )
                        text = _tool_result_text(result)
                        logs.append(
                            ToolCallLog(
                                name=call.function.name,
                                arguments=args,
                                duration_ms=int((time.perf_counter() - start) * 1000),
                                preview=_preview(text),
                            )
                        )
                        _emit(progress, f"工具完成：{call.function.name}（{logs[-1].duration_ms} ms）。")
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.id,
                                "content": text,
                            }
                        )

                _emit(progress, "工具轮次预算已用尽，正在要求模型基于已有证据收束。")
                messages.append(
                    {
                        "role": "system",
                        "content": (
                            "你已经达到工具调用轮次预算。不要再调用工具。"
                            "请只基于已有工具结果输出阶段性中文 Markdown 报告；"
                            "若证据不足，请明确说明缺口和建议下一步。"
                        ),
                    }
                )
                response = await _with_timeout(
                    client.chat.completions.create(
                        model=selected_model,
                        messages=messages,
                    ),
                    config.limits.llm_timeout_seconds,
                    "LLM 收束请求",
                )
                message = response.choices[0].message
                return AnalysisResult(
                    mode=selected_mode,
                    repo_path=str(guard.session_repo),
                    markdown=message.content or "## 结论\n\n工具轮次预算已用尽，且模型没有返回可用内容。",
                    tool_calls=logs,
                )
    finally:
        await client.close()

    raise RuntimeError("MCP 会话意外结束，未能生成报告。")


async def chat_without_tools(
    message: str,
    *,
    context: str = "",
    config_path: str | Path | None = None,
    offline: bool = False,
) -> str:
    """Answer a normal chat turn without exposing MCP tools."""

    config = load_config(config_path)
    if offline or not config.llm.api_key or not config.llm.base_url or not config.llm.model:
        return ""
    client = AsyncOpenAI(api_key=config.llm.api_key, base_url=config.llm.base_url, timeout=config.limits.llm_timeout_seconds)
    user_content = message if not context else f"{message}\n\n当前会话上下文：\n{context}"
    try:
        response = await _with_timeout(
            client.chat.completions.create(
                model=config.llm.model,
                messages=[
                    {"role": "system", "content": _load_chat_prompt()},
                    {"role": "user", "content": user_content},
                ],
            ),
            config.limits.llm_timeout_seconds,
            "普通对话请求",
        )
        return response.choices[0].message.content or ""
    finally:
        await client.close()


def run_analysis(*args: Any, **kwargs: Any) -> AnalysisResult:
    return asyncio.run(analyze_repository(*args, **kwargs))


def run_plain_chat(*args: Any, **kwargs: Any) -> str:
    return asyncio.run(chat_without_tools(*args, **kwargs))
