"""Command-line interface for RepoPilot."""

from __future__ import annotations

import json
import sys
import time
from getpass import getpass
from pathlib import Path
from typing import Annotated, Callable, Any

import click
import typer
import uvicorn
from rich import box
from rich.align import Align
from rich.console import Console
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import __version__
from .agent import AnalysisResult, run_analysis
from .config import append_readable_root, load_config, with_report_dir
from .intent import validate_slash_command
from .permissions import PathGuard, PermissionErrorDetail
from .session import ChatSession
from .settings_store import (
    add_readable_root,
    clean_runtime_home,
    ensure_local_settings,
    flatten_config,
    get_config_value,
    merge_with_defaults,
    remove_readable_root,
    reset_config_value,
    RuntimeCleanPlan,
    runtime_clean_plan,
    runtime_home_summary,
    select_config_document,
    settings_health,
    set_network_enabled,
    set_config_value,
    update_env_value,
    default_config_data,
    ensure_repo_profile,
)
from .tools.repository import SaveReportInput, repo_save_report


app = typer.Typer(
    help=(
        "RepoPilot：面向陌生代码仓库的只读优先 MCP 入职侦察 Agent。\n\n"
        "直接运行 `repopilot` 会进入引导式 CLI；子命令适合脚本化和快速操作。"
    ),
    no_args_is_help=False,
    rich_markup_mode="rich",
)
config_app = typer.Typer(help="查看和修改 RepoPilot 本地配置。", no_args_is_help=True, rich_markup_mode="rich")
network_app = typer.Typer(help="管理联网工具开关。", no_args_is_help=True, rich_markup_mode="rich")
console = Console()

TITLE_ABOUT = "关于 / About"
TITLE_ACTIONS = "快速动作 / Actions"
TITLE_ANSWER = "回复 / Answer"
TITLE_ARTIFACTS = "报告列表 / Artifacts"
TITLE_CHAT = "会话状态 / Status"
TITLE_COMMAND = "命令 / Command"
TITLE_CONFIG = "配置 / Config"
TITLE_ERROR = "错误 / Error"
TITLE_HELP = "帮助 / Help"
TITLE_INPUT = "输入规则 / Input"
TITLE_PROVIDER = "模型供应商 / Provider"
TITLE_REPORT = "报告 / Report"
TITLE_SETTINGS = "设置 / Settings"
TITLE_SETUP = "初始化 / Setup"
TITLE_SOURCES = "证据 / Sources"
TITLE_STATUS = "状态 / Status"
TITLE_THINKING = "运行中 / Thinking"
TITLE_TOOLS = "工具 / Tools"
TITLE_TRACE = "执行轨迹 / Trace"
TITLE_USER = "你 / You"

LOGO_TEXT = r"""
    ____                   ____  _ __      __
   / __ \___  ____  ____  / __ \(_) /___  / /_
  / /_/ / _ \/ __ \/ __ \/ /_/ / / / __ \/ __/
 / _, _/  __/ /_/ / /_/ / ____/ / / /_/ / /_
/_/ |_|\___/ .___/\____/_/   /_/_/\____/\__/
          /_/
""".strip("\n")

MODE_LABELS = {
    "overview": "仓库概览",
    "runbook": "运行手册",
    "module-map": "模块地图",
    "task-brief": "任务简报",
    "deep-scan": "完整入职包",
    "chat": "自然对话",
}

PROVIDER_PRESETS: dict[str, tuple[str, str, str]] = {
    "openai": ("OpenAI", "https://api.openai.com/v1", "gpt-5-mini"),
    "gemini": ("Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai/", "gemini-2.5-flash"),
    "deepseek": ("DeepSeek", "https://api.deepseek.com", "deepseek-v4-flash"),
    "qwen": ("Alibaba Qwen / DashScope", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus"),
    "kimi": ("Moonshot Kimi", "https://api.moonshot.cn/v1", "kimi-k2.5"),
    "zhipu": ("Zhipu GLM", "https://open.bigmodel.cn/api/paas/v4/", "glm-5.1"),
    "openrouter": ("OpenRouter", "https://openrouter.ai/api/v1", "openrouter/auto"),
    "groq": ("Groq", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "siliconflow": ("SiliconFlow", "https://api.siliconflow.cn/v1", "deepseek-ai/DeepSeek-V3"),
}


def _console_safe(text: str) -> str:
    encoding = console.file.encoding or sys.stdout.encoding or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def _hard_clear() -> None:
    console.file.write("\033[2J\033[3J\033[H")
    console.file.flush()
    console.clear()


def _set_terminal_title(title: str) -> None:
    if not console.is_terminal:
        return
    safe_title = title.replace("\a", "").replace("\033", "").strip()
    if not safe_title:
        return
    console.file.write(f"\033]0;{safe_title}\a")
    console.file.flush()


def _is_compact(config_path: str | Path | None = None) -> bool:
    try:
        compact_width = load_config(config_path).ui.compact_width
    except Exception:
        compact_width = 92
    return console.width < compact_width


def _use_animation(config_path: str | Path | None = None) -> bool:
    if not console.is_terminal:
        return False
    try:
        return load_config(config_path).ui.animations
    except Exception:
        return True


def _show_user_turn(config_path: str | Path | None = None) -> bool:
    try:
        return load_config(config_path).ui.show_user_turns
    except Exception:
        return True


def _keep_progress_log(config_path: str | Path | None = None) -> bool:
    try:
        return load_config(config_path).ui.keep_progress_log
    except Exception:
        return False


def _short_path(path: str, max_chars: int = 56) -> str:
    text = str(path)
    if len(text) <= max_chars:
        return text
    keep = max(12, (max_chars - 3) // 2)
    return f"{text[:keep]}...{text[-keep:]}"


def _status_label(enabled: bool) -> str:
    return "[green]on[/green]" if enabled else "[red]off[/red]"


def _preview_text(text: str, limit: int = 180) -> str:
    compact = " ".join(str(text).split())
    return compact[:limit] + ("..." if len(compact) > limit else "")


def _panel(content: Any, title: str, style: str = "cyan") -> Panel:
    if isinstance(content, str):
        content = _console_safe(content.strip())
    return Panel(content, title=title, border_style=style, box=box.ROUNDED, expand=True)


def _message(text: str, title: str = "RepoPilot", style: str = "cyan") -> None:
    console.print(_panel(text, title, style))


def _data_table() -> Table:
    return Table(show_lines=False, box=box.SIMPLE_HEAVY, expand=True)


def _print_table(table: Table, title: str, style: str = "blue") -> None:
    console.print(_panel(table, title, style))


def _format_token_usage(token_usage: Any | None) -> str | None:
    total = getattr(token_usage, "total_tokens", 0) if token_usage else 0
    return f"{int(total):,} tokens" if total else None


def _turn_divider(
    status: str = "已完成",
    elapsed_seconds: float | None = None,
    tool_calls: int | None = None,
    token_usage: Any | None = None,
    show_missing_tokens: bool = False,
) -> None:
    parts = [status]
    if elapsed_seconds is not None:
        parts.append(f"{elapsed_seconds:.1f}s")
    if tool_calls is not None:
        parts.append(f"工具调用 {tool_calls}")
    token_text = _format_token_usage(token_usage)
    if token_text:
        parts.append(token_text)
    elif show_missing_tokens:
        parts.append("token 未返回")
    text = Text(f"─ {' · '.join(parts)} ─", style="dim")
    console.print(Align.center(text))


def _progress_log_panel(events: list[str]) -> None:
    if not events:
        return
    table = _data_table()
    table.add_column("#", justify="right", style="dim", no_wrap=True)
    table.add_column("事件")
    for index, event in enumerate(events, start=1):
        table.add_row(str(index), _console_safe(_preview_text(event, 140)))
    _print_table(table, TITLE_TRACE, "magenta")


def _logo_panel(config_path: str | Path | None = None) -> Panel:
    try:
        logo = load_config(config_path).ui.logo
    except Exception:
        logo = "compact"
    if logo == "none":
        title = Text("RepoPilot", style="bold cyan")
    else:
        title = Text(f"\n{LOGO_TEXT}\n", style="bold cyan")
    body = Group(
        Align.center(title),
        Align.center(Text("Read-only repository reconnaissance agent", style="dim")),
    )
    return _panel(body, f"RepoPilot / v{__version__}", "cyan")


def _select_provider() -> bool:
    current = load_config()
    if current.llm.provider or current.llm.base_url or current.llm.model:
        table = Table.grid(padding=(0, 1))
        table.add_column(style="dim", no_wrap=True)
        table.add_column()
        table.add_row("供应商 / Provider", current.llm.provider or "<empty>")
        table.add_row("Base URL", current.llm.base_url or "<empty>")
        table.add_row("Model", current.llm.model or "<empty>")
        console.print(_panel(table, TITLE_PROVIDER, "blue"))
        if not typer.confirm("是否修改 LLM 供应商配置？", default=False):
            _message("已取消，现有供应商配置保持不变。", TITLE_PROVIDER, "yellow")
            return False
    table = _data_table()
    table.add_column("编号")
    table.add_column("供应商")
    table.add_column("Base URL")
    table.add_column("默认模型")
    preset_items = list(PROVIDER_PRESETS.items())
    for index, (_, preset) in enumerate(preset_items, start=1):
        table.add_row(str(index), preset[0], preset[1], preset[2])
    custom_choice = str(len(preset_items) + 1)
    table.add_row(custom_choice, "OpenAI-compatible 自定义", "手动输入", "手动输入")
    _print_table(table, TITLE_PROVIDER, "blue")
    while True:
        choice = typer.prompt("供应商编号").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(preset_items):
            _, (provider, base_url, model) = preset_items[int(choice) - 1]
            break
        if choice == custom_choice:
            provider = typer.prompt("供应商名称", default="custom").strip()
            base_url = typer.prompt("Base URL").strip()
            model = typer.prompt("模型名称").strip()
            break
        _message(f"请输入 1 到 {custom_choice} 之间的编号。", TITLE_PROVIDER, "yellow")
    update_env_value("LLM_PROVIDER", provider)
    update_env_value("LLM_BASE_URL", base_url)
    update_env_value("LLM_MODEL", model)
    _message(f"已选择供应商：{provider} / {model}", TITLE_PROVIDER, "green")
    return True


def _show_result(result: AnalysisResult) -> None:
    table = _data_table()
    table.add_column("工具")
    table.add_column("耗时")
    table.add_column("摘要")
    for item in result.tool_calls:
        table.add_row(item.name, f"{item.duration_ms} ms", _console_safe(_preview_text(item.preview)))
    if result.tool_calls:
        _print_table(table, TITLE_TRACE, "magenta")
    meta = f"{result.mode} | {len(result.tool_calls)} tool calls | {'offline' if result.offline else 'online'}"
    console.print(_panel(result.markdown, f"{TITLE_REPORT} · {meta}", "cyan"))


def _save_if_needed(result: AnalysisResult, save: bool, config_path: str | None) -> str | None:
    if not save:
        return None
    filename = f"{Path(result.repo_path).name}-{result.mode}.md"
    profile = ensure_repo_profile(result.repo_path)
    config = with_report_dir(load_config(config_path), profile.reports_dir)
    text = repo_save_report(SaveReportInput(filename=filename, content=result.markdown), config)
    _message(text, TITLE_STATUS, "green")
    return text


def _result_payload(result: AnalysisResult, saved: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "mode": result.mode,
        "repo_path": result.repo_path,
        "markdown": result.markdown,
        "offline": result.offline,
        "saved": saved,
        "tool_calls": [
            {
                "name": call.name,
                "arguments": call.arguments,
                "duration_ms": call.duration_ms,
                "preview": call.preview,
            }
            for call in result.tool_calls
        ],
    }
    if result.token_usage:
        payload["token_usage"] = {
            "prompt_tokens": result.token_usage.prompt_tokens,
            "completion_tokens": result.token_usage.completion_tokens,
            "total_tokens": result.token_usage.total_tokens,
        }
    return payload


def _format_exception(exc: BaseException) -> str:
    if isinstance(exc, BaseExceptionGroup):
        lines = [str(exc)]
        for index, item in enumerate(exc.exceptions, start=1):
            lines.append(f"{index}. {_format_exception(item)}")
        return "\n".join(lines)
    cause = exc.__cause__ or exc.__context__
    if cause:
        return f"{exc}\n原因：{_format_exception(cause)}"
    return str(exc)


def _authorize_repo_if_needed(repo_path: str, config_path: str | None) -> None:
    config = load_config(config_path)
    try:
        PathGuard(config, repo_path)
    except PermissionErrorDetail as exc:
        message = str(exc)
        if "readable_roots" not in message:
            raise
        _message(message, "权限 / Permission", "yellow")
        if config_path:
            prompt = f"是否将该仓库的绝对路径加入配置文件 {config_path} 并继续？"
        else:
            prompt = "是否将该仓库的绝对路径加入 RepoPilot home 配置并继续？"
        if not typer.confirm(prompt, default=False):
            raise typer.Abort()
        selected = append_readable_root(config_path, repo_path)
        _message(f"已更新配置：{selected}", TITLE_CONFIG, "green")
    ensure_repo_profile(repo_path)


def _print_progress(message: str) -> None:
    console.print(f"[dim]RepoPilot[/dim] {_console_safe(message)}")


def _print_user_turn(text: str, config_path: str | Path | None = None) -> None:
    if not _show_user_turn(config_path):
        return
    console.print(_panel(_console_safe(text), TITLE_USER, "bright_black"))


CHAT_COMMANDS = [
    ("起步", "/help [group]", "显示命令；分组支持 chat/config/mcp/reports"),
    ("起步", "/status", "显示会话状态"),
    ("分析", "/overview", "生成仓库概览"),
    ("分析", "/runbook", "生成运行手册"),
    ("分析", "/module-map", "生成模块地图"),
    ("分析", "/task-brief <task>", "围绕任务生成简报"),
    ("分析", "/deep-scan", "生成完整仓库入职包"),
    ("工具", "/mcp [on|off]", "显示 MCP 状态或开关联网工具"),
    ("工具", "/tools", "显示本轮可用工具"),
    ("证据", "/sources", "显示工具证据摘要"),
    ("证据", "/artifacts", "显示会话报告"),
    ("证据", "/save [name]", "保存最近一份报告"),
    ("配置", "/config", "显示当前配置摘要"),
    ("配置", "/settings [get|set|reset]", "查看或修改 YAML 配置"),
    ("配置", "/provider", "更改 LLM 供应商"),
    ("配置", "/api-key", "更改 LLM API Key"),
    ("配置", "/setup", "初始化运行时配置"),
    ("会话", "/clear", "清空当前会话"),
    ("会话", "/exit", "退出"),
]


def _run(
    mode: str,
    repo_path: str,
    task: str | None,
    config: str | None,
    offline: bool,
    save: bool,
    json_output: bool = False,
) -> None:
    try:
        _authorize_repo_if_needed(repo_path, config)
        if json_output:
            result = run_analysis(mode, repo_path, task, config_path=config, offline=offline, progress=None)
        elif _use_animation(config):
            latest = f"准备执行 {mode}。"

            with console.status(_console_safe(latest), spinner="dots") as status:

                def progress(message: str) -> None:
                    nonlocal latest
                    latest = message
                    status.update(_console_safe(message))

                result = run_analysis(mode, repo_path, task, config_path=config, offline=offline, progress=progress)
        else:
            result = run_analysis(mode, repo_path, task, config_path=config, offline=offline, progress=_print_progress)
    except typer.Abort:
        raise
    except Exception as exc:
        raise click.ClickException(_format_exception(exc)) from exc
    if json_output:
        saved = None
        if save:
            filename = f"{Path(result.repo_path).name}-{result.mode}.md"
            report_config = load_config(config)
            if config is None:
                profile = ensure_repo_profile(result.repo_path)
                report_config = with_report_dir(report_config, profile.reports_dir)
            saved = repo_save_report(SaveReportInput(filename=filename, content=result.markdown), report_config)
        console.print_json(json.dumps(_result_payload(result, saved), ensure_ascii=False))
        return
    _show_result(result)
    _save_if_needed(result, save, config)


def _print_session_header(session: ChatSession) -> None:
    config = load_config(session.config_path)
    mcp = session.get_mcp_status()
    table = Table.grid(padding=(0, 1))
    table.add_column(style="dim", no_wrap=True)
    table.add_column()
    table.add_row("仓库 / Repo", _console_safe(_short_path(session.state.repo_path, 64)))
    table.add_row("模型 / Model", _console_safe(config.llm.model or "<empty>"))
    table.add_row("MCP", f"{mcp.transport} / {len(mcp.tools)} tools")
    table.add_row("联网 / Network", _status_label(mcp.network_enabled))
    table.add_row("离线 / Offline", _status_label(session.offline))
    console.print(_panel(table, TITLE_CHAT, "cyan"))


def _print_banner(config_path: str | Path | None = None) -> None:
    console.print(_logo_panel(config_path))


def _quick_actions_panel() -> Panel:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="cyan", no_wrap=True)
    table.add_column()
    table.add_row("/overview", "仓库概览")
    table.add_row("/runbook", "运行手册")
    table.add_row("/module-map", "模块地图")
    table.add_row("/task-brief <task>", "任务简报")
    table.add_row("/deep-scan", "完整入职包")
    return _panel(table, TITLE_ACTIONS, "blue")


def _input_rules_panel() -> Panel:
    body = "\n".join(
        [
            "[cyan]/help[/cyan] 查看命令  [cyan]/status[/cyan] 查看状态  [cyan]/exit[/cyan] 退出",
            "直接输入自然语言即可追问；以 [cyan]/[/cyan] 开头的输入只按命令解析。",
        ]
    )
    return _panel(body, TITLE_INPUT, "magenta")


def _about_panel() -> Panel:
    body = Align.center(Text("lte_z · 小Z工作室#2026", style="#ffa500"))
    return _panel(body, TITLE_ABOUT, "#ffa500")


def _print_dashboard(session: ChatSession) -> None:
    _print_banner(session.config_path)
    _print_session_header(session)
    if _is_compact(session.config_path):
        console.print(_quick_actions_panel())
        console.print(_input_rules_panel())
        console.print(_about_panel())
        return
    grid = Table.grid(expand=True)
    grid.add_column(ratio=1)
    grid.add_column(ratio=1)
    grid.add_row(_quick_actions_panel(), Group(_input_rules_panel(), _about_panel()))
    console.print(grid)


def _chat_help_table() -> Table:
    table = _data_table()
    table.add_column("分类", style="blue", no_wrap=True)
    table.add_column("命令", style="cyan", no_wrap=True)
    table.add_column("说明")
    previous_group = ""
    for group, command, description in CHAT_COMMANDS:
        table.add_row(group if group != previous_group else "", command, description)
        previous_group = group
    table.caption = "完整命令参考：docs/cli-reference.md\n以 / 开头的输入只按命令解析"
    return table


def _chat_help_for_group(group: str) -> Table:
    groups: dict[str, list[tuple[str, str]]] = {
        "chat": [
            ("/overview", "生成仓库概览"),
            ("/runbook", "生成运行手册"),
            ("/module-map", "生成模块地图"),
            ("/task-brief <task>", "围绕任务生成简报"),
            ("/deep-scan", "生成完整仓库入职包"),
            ("自然语言", "普通提问会先识别意图，需要仓库证据时才调用工具"),
        ],
        "config": [
            ("/settings", "显示 YAML 配置"),
            ("/settings get <key>", "读取配置项"),
            ("/settings set <key> <value>", "修改配置项"),
            ("/settings reset <key>", "恢复默认值"),
            ("/provider / /api-key", "修改 LLM 连接信息"),
            ("/setup", "初始化运行时配置"),
            ("repopilot config home", "查看 RepoPilot home 保存的数据"),
            ("repopilot config clean", "清理 RepoPilot home"),
        ],
        "mcp": [
            ("/mcp", "显示 MCP 工具状态"),
            ("/mcp on", "开启 HTTP Fetch 工具"),
            ("/mcp off", "关闭 HTTP Fetch 工具"),
            ("/tools", "列出当前可用工具"),
        ],
        "reports": [
            ("/artifacts", "列出会话报告"),
            ("/sources", "列出工具证据摘要"),
            ("/save [name]", "保存最近报告到当前仓库 profile reports"),
        ],
    }
    table = _data_table()
    table.add_column("命令", style="cyan", no_wrap=True)
    table.add_column("说明")
    for command, description in groups[group]:
        table.add_row(command, description)
    table.caption = "完整命令参考：docs/cli-reference.md"
    return table


def _mcp_table(config_path: str | None = None) -> Table:
    config = load_config(config_path)
    tools = [
        ("repo_list_tree", "读取受限目录树"),
        ("repo_read_file", "读取受限文本文件"),
        ("repo_search_text", "搜索仓库文本"),
        ("repo_detect_stack", "识别技术栈线索"),
        ("repo_git_summary", "读取 Git 摘要"),
        ("repo_symbol_map", "生成代码符号地图"),
        ("repo_save_report", "保存 Markdown 报告"),
    ]
    if config.network.allow_http_fetch:
        tools.append(("web_fetch_url", "读取允许域名范围内的网页文本"))
    table = _data_table()
    table.add_column("工具")
    table.add_column("状态")
    table.add_column("说明")
    for name, description in tools:
        table.add_row(name, "on", description)
    if not config.network.allow_http_fetch:
        table.add_row("web_fetch_url", "off", "HTTP Fetch 已关闭")
    return table


def _artifact_panel_title(artifact) -> str:
    if artifact.mode == "chat":
        if artifact.title == "对话":
            return TITLE_ANSWER
        return f"{TITLE_ANSWER} · {artifact.title}"
    label = MODE_LABELS.get(artifact.mode, artifact.mode)
    return f"{TITLE_REPORT} · {label}"


def _print_artifact(artifact) -> None:
    style = "cyan" if artifact.mode == "chat" else "blue"
    console.print(_panel(artifact.markdown, _console_safe(_artifact_panel_title(artifact)), style))


def _tools_table(session: ChatSession) -> Table:
    table = _data_table()
    table.add_column("工具", style="cyan", no_wrap=True)
    table.add_column("状态", no_wrap=True)
    for name in session.get_mcp_status().tools:
        table.add_row(name, "on")
    return table


def _sources_table(session: ChatSession) -> Table | Panel:
    sources = session.get_sources()
    if not sources:
        return _panel("暂无工具证据。", TITLE_SOURCES, "bright_black")
    table = _data_table()
    table.add_column("#", justify="right", style="dim", no_wrap=True)
    table.add_column("工具", style="cyan", no_wrap=True)
    table.add_column("摘要")
    for index, item in enumerate(sources[-20:], start=1):
        table.add_row(str(index), item.label, _console_safe(_preview_text(item.detail, 180)))
    return table


def _artifacts_table(session: ChatSession) -> Table | Panel:
    if not session.state.artifacts:
        return _panel("暂无报告。", TITLE_ARTIFACTS, "bright_black")
    table = _data_table()
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("模式", no_wrap=True)
    table.add_column("标题")
    table.add_column("已保存", no_wrap=True)
    for item in session.state.artifacts:
        table.add_row(item.id, MODE_LABELS.get(item.mode, item.mode), _console_safe(item.title), "是" if item.saved_path else "否")
    return table


def _set_api_key_interactive() -> bool:
    ensure_local_settings()
    config = load_config()
    if not config.llm.provider or not config.llm.base_url or not config.llm.model:
        _message("请先选择 LLM 供应商。", TITLE_PROVIDER, "yellow")
        if not _select_provider():
            return False
        config = load_config()
    if config.llm.api_key:
        _message("当前已保存 API Key。继续会覆盖旧值，直接取消则保持不变。", "API Key", "yellow")
        if not typer.confirm("是否修改 API Key？", default=False):
            _message("已取消，现有 API Key 保持不变。", "API Key", "yellow")
            return False
    key = getpass("LLM API Key: ").strip()
    if not key:
        _message("已取消，现有 API Key 保持不变。", "API Key", "yellow")
        return False
    update_env_value("LLM_API_KEY", key)
    _message("API Key 已保存。", "API Key", "green")
    return True


def _handle_chat_command(session: ChatSession, command: str) -> bool:
    validation_error = validate_slash_command(command)
    if validation_error:
        _message(validation_error, TITLE_COMMAND, "yellow")
        return True
    name, _, rest = command.partition(" ")
    if name in ("/exit", "/quit"):
        return False
    if name == "/help":
        group = rest.strip()
        _print_table(_chat_help_for_group(group) if group else _chat_help_table(), TITLE_HELP, "blue")
    elif name == "/setup":
        config_path, env_path = ensure_local_settings()
        _message(f"配置文件：{config_path}\n环境文件：{env_path}", TITLE_SETUP, "green")
    elif name == "/config":
        _print_table(_settings_table(session.config_path), TITLE_SETTINGS, "blue")
    elif name == "/settings":
        _handle_settings_command(session.config_path, rest)
        session.config = load_config(session.config_path)
    elif name == "/provider":
        changed = _select_provider()
        session.config = load_config(session.config_path)
        if changed:
            _print_table(_settings_table(session.config_path), TITLE_SETTINGS, "blue")
    elif name == "/api-key":
        changed = _set_api_key_interactive()
        session.config = load_config(session.config_path)
        if changed:
            _print_table(_settings_table(session.config_path), TITLE_SETTINGS, "blue")
    elif name == "/status":
        _print_session_header(session)
    elif name == "/task-brief":
        _message("/task-brief 需要任务文本。", TITLE_COMMAND, "yellow")
    elif name == "/mcp":
        action = rest.strip().lower()
        if action in ("on", "off"):
            set_network_enabled(action == "on", session.config_path)
            session.config = load_config(session.config_path)
            _message(f"HTTP Fetch 已{'开启' if action == 'on' else '关闭'}。", "MCP", "green")
        elif action:
            _message("用法：/mcp、/mcp on 或 /mcp off。", "MCP", "yellow")
        _print_table(_mcp_table(session.config_path), "MCP", "blue")
    elif name == "/tools":
        _print_table(_tools_table(session), TITLE_TOOLS, "blue")
    elif name == "/sources":
        output = _sources_table(session)
        console.print(output) if isinstance(output, Panel) else _print_table(output, TITLE_SOURCES, "blue")
    elif name == "/artifacts":
        output = _artifacts_table(session)
        console.print(output) if isinstance(output, Panel) else _print_table(output, TITLE_ARTIFACTS, "blue")
    elif name == "/save":
        _message(session.save_artifact(filename=rest.strip() or None), TITLE_STATUS, "green")
    elif name == "/clear":
        if typer.confirm("确认清空当前会话上下文并清屏？", default=False):
            session.clear()
            _hard_clear()
            _print_dashboard(session)
        else:
            _message("已取消，当前会话保持不变。", "清空 / Clear", "yellow")
    else:
        _message(f"未知命令：{name}。输入 /help 查看命令。", TITLE_COMMAND, "yellow")
    return True


def _run_chat_action(
    label: str,
    action: Callable[[Callable[[str], None]], object],
    config_path: str | Path | None = None,
) -> bool:
    latest = label
    events: list[str] = []
    start = time.perf_counter()
    status = "已完成"
    artifact = None

    def progress(message: str) -> None:
        nonlocal latest
        latest = message
        events.append(message)
        console.print(f"[magenta]运行中[/magenta] [dim]{_console_safe(message)}[/dim]")

    try:
        console.print(_panel(label, TITLE_THINKING, "magenta"))
        if _use_animation(config_path):
            with console.status(_console_safe(label), spinner="dots") as spinner:

                def animated_progress(message: str) -> None:
                    nonlocal latest
                    latest = message
                    events.append(message)
                    spinner.update(_console_safe(message))

                artifact = action(animated_progress)
        else:
            artifact = action(progress)
        if _keep_progress_log(config_path):
            _progress_log_panel(events)
        _print_artifact(artifact)
    except KeyboardInterrupt:
        status = "已中断"
        _message("已尝试中断当前操作。你可以继续输入命令，或输入 /exit 退出。", "中断 / Interrupted", "yellow")
    except Exception as exc:
        status = "失败"
        _message(_format_exception(exc), TITLE_ERROR, "red")
    finally:
        if latest == label and status == "已完成":
            status = "未执行"
        tool_calls = sum(1 for event in events if event.startswith("调用工具："))
        token_usage = getattr(artifact, "token_usage", None)
        show_missing_tokens = status in {"已完成", "已中断", "失败"}
        _turn_divider(status, time.perf_counter() - start, tool_calls, token_usage, show_missing_tokens)
    return status == "已完成"


def _chat_loop(session: ChatSession) -> None:
    _print_dashboard(session)
    while True:
        console.print()
        try:
            text = console.input("[bold cyan]RepoPilot>[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        if not text:
            continue
        try:
            _print_user_turn(text, session.config_path)
            if text.startswith("/"):
                validation_error = validate_slash_command(text)
                if validation_error:
                    _message(validation_error, TITLE_COMMAND, "yellow")
                    continue
                name, _, rest = text.partition(" ")
                if name == "/overview":
                    _run_chat_action(
                        "生成仓库概览。按 Ctrl+C 可尝试中断。",
                        lambda progress: session.run_quick_action("overview", progress=progress),
                        session.config_path,
                    )
                elif name == "/runbook":
                    _run_chat_action(
                        "生成运行手册。按 Ctrl+C 可尝试中断。",
                        lambda progress: session.run_quick_action("runbook", progress=progress),
                        session.config_path,
                    )
                elif name == "/module-map":
                    _run_chat_action(
                        "生成模块地图。按 Ctrl+C 可尝试中断。",
                        lambda progress: session.run_quick_action("module-map", progress=progress),
                        session.config_path,
                    )
                elif name == "/task-brief" and rest.strip():
                    _run_chat_action(
                        "生成任务简报。按 Ctrl+C 可尝试中断。",
                        lambda progress: session.run_quick_action("task-brief", rest.strip(), progress=progress),
                        session.config_path,
                    )
                elif name == "/deep-scan":
                    _run_chat_action(
                        "生成完整仓库入职包。按 Ctrl+C 可尝试中断。",
                        lambda progress: session.run_quick_action("deep-scan", progress=progress),
                        session.config_path,
                    )
                elif not _handle_chat_command(session, text):
                    break
            else:
                _run_chat_action(
                    "处理追问。按 Ctrl+C 可尝试中断。",
                    lambda progress: session.send_message(text, progress=progress),
                    session.config_path,
                )
        except Exception as exc:
            _message(_format_exception(exc), TITLE_ERROR, "red")


def _start_chat(repo_path: str, config_path: str | None, offline: bool, *, clear_screen: bool = True) -> None:
    _authorize_repo_if_needed(repo_path, config_path)
    session = ChatSession(repo_path, config_path=config_path, offline=offline)
    _set_terminal_title(f"RepoPilot / v{__version__} · {Path(session.state.repo_path).name}")
    if clear_screen:
        _hard_clear()
    _chat_loop(session)


def _guided_entry() -> None:
    _set_terminal_title(f"RepoPilot / v{__version__}")
    _hard_clear()
    ensure_local_settings()
    _print_banner()
    config = load_config()
    offline = False
    if not config.llm.provider or not config.llm.base_url or not config.llm.model:
        _message("尚未选择 LLM 供应商。", TITLE_SETUP, "yellow")
        if typer.confirm("现在选择供应商并使用在线 Agent？", default=False):
            _select_provider()
            config = load_config()
        else:
            offline = True
            _message("本次将使用离线模式，你仍然可以验证仓库工具链和报告保存。", "离线 / Offline", "yellow")
    if not offline and not config.llm.api_key:
        _message("尚未配置 LLM_API_KEY。", TITLE_SETUP, "yellow")
        if typer.confirm("现在填写 API Key？", default=False):
            key = getpass("LLM API Key: ").strip()
            if key:
                update_env_value("LLM_API_KEY", key)
                config = load_config()
            else:
                offline = True
        else:
            offline = True
            _message("本次将使用离线模式，你仍然可以验证仓库工具链和报告保存。", "离线 / Offline", "yellow")
    default_repo = str(Path.cwd().resolve())
    repo_path = typer.prompt("选择要分析的仓库路径", default=default_repo)
    try:
        _start_chat(repo_path, None, offline, clear_screen=True)
    except typer.Abort:
        raise
    except Exception as exc:
        raise click.ClickException(_format_exception(exc)) from exc


ConfigOption = Annotated[str | None, typer.Option("--config", help="配置文件路径。")]
OfflineOption = Annotated[bool, typer.Option("--offline", help="使用离线工具摘要模式，不调用 LLM。")]
SaveOption = Annotated[bool, typer.Option("--save", help="保存 Markdown 报告到当前仓库 profile reports。")]
JsonOption = Annotated[bool, typer.Option("--json", help="输出机器可读 JSON，不显示 Rich 表格。")]


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """不带子命令时进入引导式交互入口。"""

    if ctx.invoked_subcommand is None:
        _guided_entry()


def _mask_secret(value: str) -> str:
    if not value:
        return "<empty>"
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "*" * (len(value) - 8) + value[-4:]


def _settings_table(config_path: str | None = None) -> Table:
    config = load_config(config_path)
    health = settings_health(config.config_path)
    table = _data_table()
    table.add_column("项目")
    table.add_column("值")
    table.add_row("配置目录", str(health.store_dir))
    table.add_row("配置文件", str(health.config_path))
    table.add_row("环境文件", str(health.env_path))
    table.add_row("供应商", config.llm.provider or "<empty>")
    table.add_row("模型", config.llm.model)
    table.add_row("Base URL", config.llm.base_url)
    table.add_row("API Key", _mask_secret(config.llm.api_key))
    table.add_row("HTTP Fetch", "on" if config.network.allow_http_fetch else "off")
    table.add_row("Animations", "on" if config.ui.animations else "off")
    table.add_row("User turns", "on" if config.ui.show_user_turns else "off")
    table.add_row("readable_roots", "\n".join(config.permissions.readable_roots) or "<empty>")
    table.add_row("writable_roots", "\n".join(config.permissions.writable_roots) or "<empty>")
    return table


def _value_text(value: Any) -> str:
    if isinstance(value, (dict, list)):
        import yaml

        return yaml.safe_dump(value, allow_unicode=True, sort_keys=False).strip()
    return str(value)


def _settings_keys_table(config_path: str | None = None) -> Table:
    config = load_config(config_path)
    data = default_config_data()
    try:
        _, data = select_config_document(config.config_path)
        data = merge_with_defaults(data)
    except (FileNotFoundError, OSError, ValueError):
        pass
    table = _data_table()
    table.add_column("配置项", style="cyan")
    table.add_column("当前值")
    for key, value in sorted(flatten_config(data).items()):
        table.add_row(key, _value_text(value))
    table.caption = "用法：/settings get <key>、/settings set <key> <value>、/settings reset <key>"
    return table


def _handle_settings_command(config_path: str | None, rest: str) -> None:
    parts = rest.strip().split(maxsplit=2)
    if not parts:
        _print_table(_settings_keys_table(config_path), TITLE_SETTINGS, "blue")
        return
    action = parts[0]
    try:
        if action == "get" and len(parts) == 2:
            _message(f"{parts[1]} = {_value_text(get_config_value(parts[1], config_path))}", TITLE_SETTINGS, "cyan")
        elif action == "set" and len(parts) == 3:
            selected = set_config_value(parts[1], parts[2], config_path)
            _message(f"已更新 {parts[1]}：{selected}", TITLE_SETTINGS, "green")
        elif action == "reset" and len(parts) == 2:
            selected = reset_config_value(parts[1], config_path)
            _message(f"已恢复 {parts[1]} 默认值：{selected}", TITLE_SETTINGS, "green")
        else:
            _message("用法：/settings、/settings get <key>、/settings set <key> <value>、/settings reset <key>", TITLE_SETTINGS, "yellow")
    except (KeyError, ValueError) as exc:
        _message(str(exc), TITLE_SETTINGS, "yellow")


@app.command()
def overview(
    repo_path: str,
    config: ConfigOption = None,
    offline: OfflineOption = False,
    save: SaveOption = False,
    json_output: JsonOption = False,
) -> None:
    """生成仓库概览。"""

    _run("overview", repo_path, None, config, offline, save, json_output)


@app.command()
def setup(
    api_key: Annotated[str | None, typer.Option("--api-key", help="LLM API Key；不传则交互输入。")] = None,
    provider: Annotated[
        str | None,
        typer.Option(
            "--provider",
            help="内置供应商别名，例如 openai、gemini、deepseek、qwen、kimi、zhipu、openrouter、groq、siliconflow。",
        ),
    ] = None,
    base_url: Annotated[str | None, typer.Option("--base-url", help="OpenAI-compatible Base URL。")] = None,
    model: Annotated[str | None, typer.Option("--model", help="模型名称。")] = None,
    skip_api_key: Annotated[bool, typer.Option("--skip-api-key", help="只初始化配置文件，不填写 API Key。")] = False,
) -> None:
    """初始化运行时配置。"""

    config_path, env_path = ensure_local_settings()
    if provider in PROVIDER_PRESETS and not base_url and not model:
        preset_name, preset_base_url, preset_model = PROVIDER_PRESETS[provider]
        update_env_value("LLM_PROVIDER", preset_name)
        update_env_value("LLM_BASE_URL", preset_base_url)
        update_env_value("LLM_MODEL", preset_model)
    elif provider or base_url or model:
        update_env_value("LLM_PROVIDER", provider or "custom")
        update_env_value("LLM_BASE_URL", base_url or "")
        update_env_value("LLM_MODEL", model or "")
    elif not skip_api_key:
        _select_provider()
    if not skip_api_key:
        key = api_key if api_key is not None else getpass("LLM API Key: ")
        update_env_value("LLM_API_KEY", key.strip())
    _message(f"已初始化本地配置：{config_path}\n已初始化本地环境：{env_path}", TITLE_SETUP, "green")


def _runtime_home_table() -> Table:
    summary = runtime_home_summary()
    table = _data_table()
    table.add_column("项目")
    table.add_column("状态")
    table.add_row("RepoPilot home", str(summary.home))
    table.add_row("home 存在", "yes" if summary.exists else "no")
    table.add_row("home marker", "valid" if summary.marker_valid else ("missing" if not summary.marker_exists else "invalid"))
    table.add_row("config.yaml", str(summary.config_path) if summary.config_exists else "missing")
    table.add_row(".env", str(summary.env_path) if summary.env_exists else "missing")
    table.add_row("repo profiles", str(summary.repo_profiles_count))
    table.add_row("report directories", str(summary.report_dirs_count))
    table.add_row("report files", str(summary.report_files_count))
    table.add_row("total files", str(summary.total_files_count))
    table.caption = "pip uninstall 或删除虚拟环境不会自动删除 RepoPilot home。"
    return table


def _runtime_clean_table(plan: RuntimeCleanPlan, dry_run: bool) -> Table:
    table = _data_table()
    table.add_column("项目")
    table.add_column("内容")
    table.add_row("RepoPilot home", str(plan.home))
    table.add_row("状态", "不存在" if not plan.exists else ("可清理" if plan.can_clean else "拒绝清理"))
    table.add_row("说明", plan.reason)
    if plan.entries:
        table.add_row("将删除", "\n".join(str(item) for item in plan.entries))
    else:
        table.add_row("将删除", "无")
    table.caption = "dry-run：未删除任何文件。" if dry_run else "执行清理会删除配置、API Key、repo profiles 和报告。"
    return table


@config_app.command("home")
def config_home() -> None:
    """显示 RepoPilot home 保存的数据摘要。"""

    _print_table(_runtime_home_table(), "运行时目录 / Home", "blue")


@config_app.command("clean")
def config_clean(
    dry_run: Annotated[bool, typer.Option("--dry-run", help="只预览将删除的内容，不实际删除。")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="跳过二次确认。")] = False,
) -> None:
    """清理 RepoPilot home 中的配置、API Key、repo profiles 和报告。"""

    plan = runtime_clean_plan()
    _print_table(_runtime_clean_table(plan, dry_run), "清理 / Clean", "yellow" if plan.can_clean else "red")
    if dry_run or not plan.exists:
        return
    if not plan.can_clean:
        raise click.ClickException(plan.reason)
    if not yes and not typer.confirm("确认删除整个 RepoPilot home？", default=False):
        _message("已取消，RepoPilot home 保持不变。", "清理 / Clean", "yellow")
        return
    try:
        clean_runtime_home(dry_run=False)
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    _message(f"已清理 RepoPilot home：{plan.home}", "清理 / Clean", "green")


@config_app.command("show")
def config_show() -> None:
    """显示当前本地配置摘要。"""

    ensure_local_settings()
    _print_table(_settings_table(), TITLE_SETTINGS, "blue")


@config_app.command("list")
def config_list(config: ConfigOption = None) -> None:
    """列出所有 YAML 配置项。"""

    ensure_local_settings()
    _print_table(_settings_keys_table(config), TITLE_SETTINGS, "blue")


@config_app.command("get")
def config_get(key: str, config: ConfigOption = None) -> None:
    """读取单个 YAML 配置项。"""

    try:
        _message(f"{key} = {_value_text(get_config_value(key, config))}", TITLE_CONFIG, "cyan")
    except KeyError as exc:
        raise click.ClickException(str(exc)) from exc


@config_app.command("set")
def config_set(key: str, value: str, config: ConfigOption = None) -> None:
    """修改单个 YAML 配置项。"""

    try:
        selected = set_config_value(key, value, config)
    except (KeyError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    _message(f"已更新 {key}：{selected}", TITLE_CONFIG, "green")


@config_app.command("reset")
def config_reset(key: str, config: ConfigOption = None) -> None:
    """将单个 YAML 配置项恢复为默认值。"""

    try:
        selected = reset_config_value(key, config)
    except (KeyError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    _message(f"已恢复 {key} 默认值：{selected}", TITLE_CONFIG, "green")


@config_app.command("schema")
def config_schema() -> None:
    """显示默认 YAML 配置结构。"""

    import yaml

    console.print(_panel(yaml.safe_dump(default_config_data(), allow_unicode=True, sort_keys=False), TITLE_SETTINGS, "blue"))


@config_app.command("doctor")
def config_doctor() -> None:
    """检查配置是否具备运行 Agent 的基本条件。"""

    ensure_local_settings()
    config = load_config()
    health = settings_health(config.config_path)
    table = _data_table()
    table.add_column("检查项")
    table.add_column("状态")
    table.add_row("config.yaml", "ok" if health.config_exists else "missing")
    table.add_row(".env", "ok" if health.env_exists else "missing")
    table.add_row("LLM_PROVIDER", config.llm.provider or "missing")
    table.add_row("LLM_API_KEY", "ok" if health.has_api_key else "missing")
    table.add_row("LLM_MODEL", config.llm.model or "missing")
    table.add_row("readable_roots", str(health.readable_roots_count))
    table.add_row("MCP tools", "local stdio server")
    table.add_row("HTTP Fetch", "on" if config.network.allow_http_fetch else "off")
    _print_table(table, "诊断 / Doctor", "blue")
    if not health.has_api_key:
        _message("提示：运行 repopilot config set-api-key 后即可调用在线模型。", "诊断 / Doctor", "yellow")
    if not config.llm.provider or not config.llm.model:
        _message("提示：运行 repopilot config set-provider 选择供应商。", "诊断 / Doctor", "yellow")


@config_app.command("add-root")
def config_add_root(path: str) -> None:
    """将仓库或父目录加入 readable_roots。"""

    selected = add_readable_root(path)
    _message(f"已加入 readable_roots：{Path(path).expanduser().resolve()}\n配置文件：{selected}", TITLE_CONFIG, "green")


@config_app.command("remove-root")
def config_remove_root(path: str) -> None:
    """从 readable_roots 移除路径。"""

    selected = remove_readable_root(path)
    _message(f"已移除 readable_roots：{Path(path).expanduser().resolve()}\n配置文件：{selected}", TITLE_CONFIG, "green")


@config_app.command("set-model")
def config_set_model(model: str) -> None:
    """设置模型名称。"""

    selected = update_env_value("LLM_MODEL", model)
    _message(f"已设置模型：{model}\n环境文件：{selected}", TITLE_CONFIG, "green")


@config_app.command("set-base-url")
def config_set_base_url(base_url: str) -> None:
    """设置 OpenAI-compatible Base URL。"""

    selected = update_env_value("LLM_BASE_URL", base_url)
    _message(f"已设置 Base URL：{base_url}\n环境文件：{selected}", TITLE_CONFIG, "green")


@config_app.command("set-provider")
def config_set_provider() -> None:
    """交互式选择 LLM 供应商、Base URL 和模型。"""

    ensure_local_settings()
    _select_provider()


@config_app.command("set-api-key")
def config_set_api_key(
    api_key: Annotated[str | None, typer.Option("--api-key", help="不传则隐藏输入。")] = None,
) -> None:
    """设置 LLM API Key。"""

    ensure_local_settings()
    config = load_config()
    if not config.llm.provider or not config.llm.base_url or not config.llm.model:
        _message("请先选择 LLM 供应商。", TITLE_PROVIDER, "yellow")
        if not _select_provider():
            return
        config = load_config()
    if api_key is None and config.llm.api_key:
        _message("当前已保存 API Key。继续会覆盖旧值，直接取消则保持不变。", "API Key", "yellow")
        if not typer.confirm("是否修改 API Key？", default=False):
            _message("已取消，现有 API Key 保持不变。", "API Key", "yellow")
            return
    key = api_key if api_key is not None else getpass("LLM API Key: ")
    if not key.strip():
        _message("已取消，现有 API Key 保持不变。", "API Key", "yellow")
        return
    selected = update_env_value("LLM_API_KEY", key.strip())
    _message(f"已保存 API Key：{selected}", "API Key", "green")


@network_app.command("on")
def config_network_on() -> None:
    """开启 web_fetch_url MCP 工具。"""

    selected = set_network_enabled(True)
    _message(f"已开启 HTTP Fetch：{selected}", "网络 / Network", "green")


@network_app.command("off")
def config_network_off() -> None:
    """关闭 web_fetch_url MCP 工具。"""

    selected = set_network_enabled(False)
    _message(f"已关闭 HTTP Fetch：{selected}", "网络 / Network", "green")


@app.command()
def runbook(
    repo_path: str,
    config: ConfigOption = None,
    offline: OfflineOption = False,
    save: SaveOption = False,
    json_output: JsonOption = False,
) -> None:
    """推断安装、运行、测试和构建线索。"""

    _run("runbook", repo_path, None, config, offline, save, json_output)


@app.command("module-map")
def module_map(
    repo_path: str,
    config: ConfigOption = None,
    offline: OfflineOption = False,
    save: SaveOption = False,
    json_output: JsonOption = False,
) -> None:
    """生成模块地图。"""

    _run("module-map", repo_path, None, config, offline, save, json_output)


@app.command("task-brief")
def task_brief(
    repo_path: str,
    task: str,
    config: ConfigOption = None,
    offline: OfflineOption = False,
    save: SaveOption = False,
    json_output: JsonOption = False,
) -> None:
    """围绕具体任务生成侦察简报。"""

    _run("task-brief", repo_path, task, config, offline, save, json_output)


@app.command("deep-scan")
def deep_scan(
    repo_path: str,
    config: ConfigOption = None,
    offline: OfflineOption = False,
    save: SaveOption = False,
    json_output: JsonOption = False,
) -> None:
    """生成完整仓库入职包。"""

    _run("deep-scan", repo_path, None, config, offline, save, json_output)


@app.command()
def mcp(
    action: Annotated[str | None, typer.Argument(help="可选：status、on 或 off。")] = None,
    config: ConfigOption = None,
) -> None:
    """显示或修改当前 MCP 工具启用状态。"""

    normalized = (action or "status").lower()
    if normalized in ("on", "off"):
        set_network_enabled(normalized == "on", config)
        _message(f"HTTP Fetch 已{'开启' if normalized == 'on' else '关闭'}。", "MCP", "green")
    elif normalized != "status":
        raise click.ClickException("用法：repopilot mcp [status|on|off]")
    _print_table(_mcp_table(config), "MCP", "blue")


@app.command()
def chat(
    repo_path: str,
    config: ConfigOption = None,
    offline: OfflineOption = False,
) -> None:
    """进入围绕单个仓库的多轮会话。"""

    try:
        _start_chat(repo_path, config, offline, clear_screen=True)
    except typer.Abort:
        raise
    except Exception as exc:
        raise click.ClickException(_format_exception(exc)) from exc


@app.command()
def web(
    host: Annotated[str, typer.Option("--host", help="监听地址。")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", help="监听端口。")] = 8765,
) -> None:
    """启动预览版本地 WebUI。"""

    _message(f"RepoPilot preview WebUI: http://{host}:{port}", "WebUI", "green")
    uvicorn.run("repopilot.web:app", host=host, port=port, reload=False)


config_app.add_typer(network_app, name="network")
app.add_typer(config_app, name="config")


if __name__ == "__main__":
    app()
