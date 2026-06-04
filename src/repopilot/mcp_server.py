"""RepoPilot MCP server."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from repopilot.tools.network import FetchUrlInput, web_fetch_url
from repopilot.tools.repository import (
    DetectStackInput,
    GitSummaryInput,
    ListTreeInput,
    ReadFileInput,
    ResponseFormat,
    SaveReportInput,
    SearchTextInput,
    SymbolMapInput,
    repo_detect_stack,
    repo_git_summary,
    repo_list_tree,
    repo_read_file,
    repo_save_report,
    repo_search_text,
    repo_symbol_map,
)


mcp = FastMCP("repopilot")


@mcp.tool(
    name="repo_list_tree",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def mcp_repo_list_tree(
    repo_path: str,
    path: str = ".",
    max_depth: int = 3,
    max_entries: int | None = None,
    response_format: ResponseFormat = "markdown",
) -> str:
    """List a bounded directory tree inside the selected repository."""

    params = ListTreeInput(
        repo_path=repo_path,
        path=path,
        max_depth=max_depth,
        max_entries=max_entries,
        response_format=response_format,
    )
    return repo_list_tree(params)


@mcp.tool(
    name="repo_read_file",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def mcp_repo_read_file(
    repo_path: str,
    path: str,
    max_chars: int | None = None,
    response_format: ResponseFormat = "markdown",
) -> str:
    """Read a text file inside the selected repository with size and permission checks."""

    params = ReadFileInput(repo_path=repo_path, path=path, max_chars=max_chars, response_format=response_format)
    return repo_read_file(params)


@mcp.tool(
    name="repo_search_text",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def mcp_repo_search_text(
    repo_path: str,
    query: str,
    glob: str | None = None,
    max_results: int | None = None,
    response_format: ResponseFormat = "markdown",
) -> str:
    """Search text inside the selected repository with ripgrep or a local fallback."""

    params = SearchTextInput(
        repo_path=repo_path,
        query=query,
        glob=glob,
        max_results=max_results,
        response_format=response_format,
    )
    return repo_search_text(params)


@mcp.tool(
    name="repo_detect_stack",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def mcp_repo_detect_stack(repo_path: str, response_format: ResponseFormat = "markdown") -> str:
    """Detect common technology stack markers and project scripts."""

    params = DetectStackInput(repo_path=repo_path, response_format=response_format)
    return repo_detect_stack(params)


@mcp.tool(
    name="repo_symbol_map",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def mcp_repo_symbol_map(
    repo_path: str,
    include_globs: list[str] | None = None,
    max_files: int = 80,
    max_symbols_per_file: int = 40,
    response_format: ResponseFormat = "markdown",
) -> str:
    """Build a lightweight class/function symbol map for readable source files."""

    params = SymbolMapInput(
        repo_path=repo_path,
        include_globs=include_globs,
        max_files=max_files,
        max_symbols_per_file=max_symbols_per_file,
        response_format=response_format,
    )
    return repo_symbol_map(params)


@mcp.tool(
    name="repo_git_summary",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def mcp_repo_git_summary(
    repo_path: str,
    max_commits: int = 5,
    response_format: ResponseFormat = "markdown",
) -> str:
    """Read Git branch, remote, status, diff stat, and recent commit metadata."""

    params = GitSummaryInput(repo_path=repo_path, max_commits=max_commits, response_format=response_format)
    return repo_git_summary(params)


@mcp.tool(
    name="repo_save_report",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
)
async def mcp_repo_save_report(
    filename: str,
    content: str,
    response_format: ResponseFormat = "markdown",
) -> str:
    """Save a generated Markdown report under RepoPilot's configured reports directory."""

    params = SaveReportInput(filename=filename, content=content, response_format=response_format)
    return repo_save_report(params)


@mcp.tool(
    name="web_fetch_url",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def mcp_web_fetch_url(
    url: str,
    max_chars: int | None = None,
    response_format: ResponseFormat = "markdown",
) -> str:
    """Fetch bounded public HTTP(S) text content for external context."""

    params = FetchUrlInput(url=url, max_chars=max_chars, response_format=response_format)
    return web_fetch_url(params)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
