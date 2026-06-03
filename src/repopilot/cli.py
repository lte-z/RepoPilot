"""Command-line interface for RepoPilot."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
import uvicorn
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .agent import AnalysisResult, run_analysis
from .config import load_config
from .tools.repository import SaveReportInput, repo_save_report


app = typer.Typer(help="RepoPilot：面向陌生代码仓库的只读优先 MCP 入职侦察 Agent。")
console = Console()


def _show_result(result: AnalysisResult) -> None:
    table = Table(title="Tool Calls", show_lines=False)
    table.add_column("工具")
    table.add_column("耗时")
    table.add_column("摘要")
    for item in result.tool_calls:
        table.add_row(item.name, f"{item.duration_ms} ms", item.preview)
    if result.tool_calls:
        console.print(table)
    console.print(Panel(result.markdown, title=f"RepoPilot / {result.mode}"))


def _save_if_needed(result: AnalysisResult, save: bool, config_path: str | None) -> None:
    if not save:
        return
    filename = f"{Path(result.repo_path).name}-{result.mode}.md"
    text = repo_save_report(SaveReportInput(filename=filename, content=result.markdown), load_config(config_path))
    console.print(text)


def _run(
    mode: str,
    repo_path: str,
    task: str | None,
    config: str | None,
    offline: bool,
    save: bool,
) -> None:
    try:
        result = run_analysis(mode, repo_path, task, config_path=config, offline=offline)
    except Exception as exc:
        raise typer.BadParameter(str(exc)) from exc
    _show_result(result)
    _save_if_needed(result, save, config)


ConfigOption = Annotated[str | None, typer.Option("--config", help="配置文件路径。")]
OfflineOption = Annotated[bool, typer.Option("--offline", help="使用离线工具摘要模式，不调用 LLM。")]
SaveOption = Annotated[bool, typer.Option("--save", help="保存 Markdown 报告到 outputs/。")]


@app.command()
def overview(repo_path: str, config: ConfigOption = None, offline: OfflineOption = False, save: SaveOption = False) -> None:
    """生成仓库概览。"""

    _run("overview", repo_path, None, config, offline, save)


@app.command()
def runbook(repo_path: str, config: ConfigOption = None, offline: OfflineOption = False, save: SaveOption = False) -> None:
    """推断安装、运行、测试和构建线索。"""

    _run("runbook", repo_path, None, config, offline, save)


@app.command("module-map")
def module_map(repo_path: str, config: ConfigOption = None, offline: OfflineOption = False, save: SaveOption = False) -> None:
    """生成模块地图。"""

    _run("module-map", repo_path, None, config, offline, save)


@app.command("task-brief")
def task_brief(
    repo_path: str,
    task: str,
    config: ConfigOption = None,
    offline: OfflineOption = False,
    save: SaveOption = False,
) -> None:
    """围绕具体任务生成侦察简报。"""

    _run("task-brief", repo_path, task, config, offline, save)


@app.command()
def web(
    host: Annotated[str, typer.Option("--host", help="监听地址。")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", help="监听端口。")] = 8765,
) -> None:
    """启动本地 WebUI。"""

    console.print(f"RepoPilot WebUI: http://{host}:{port}")
    uvicorn.run("repopilot.web:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    app()
