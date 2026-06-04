import asyncio
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def write_config(path: Path, readable_root: Path, writable_root: Path) -> None:
    path.write_text(
        f"""
permissions:
  readable_roots:
    - {readable_root.as_posix()}
  writable_roots:
    - {writable_root.as_posix()}
  deny_patterns:
    - "**/.env"
    - "**/.git/**"
    - "**/__pycache__/**"
execution:
  allow_command_execution: false
  allowed_commands: []
limits:
  max_file_chars: 20000
  max_search_results: 50
  max_tree_entries: 300
  max_tool_rounds: 8
""",
        encoding="utf-8",
    )


def test_mcp_server_lists_and_calls_repository_tools(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    outputs = tmp_path / "outputs"
    repo.mkdir()
    outputs.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname = 'sample'\n", encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    write_config(config_path, tmp_path, outputs)

    async def run() -> None:
        env = os.environ.copy()
        env["REPOPILOT_CONFIG"] = str(config_path)
        server = StdioServerParameters(
            command=sys.executable,
            args=["-m", "repopilot.mcp_server"],
            env=env,
            cwd=Path(__file__).resolve().parents[1],
        )
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                names = {tool.name for tool in listed.tools}
                assert "repo_list_tree" in names
                assert "repo_detect_stack" in names
                assert "repo_symbol_map" in names
                assert "web_fetch_url" in names

                result = await session.call_tool(
                    "repo_detect_stack",
                    {"repo_path": str(repo), "response_format": "markdown"},
                )
                text = "\n".join(item.text for item in result.content if hasattr(item, "text"))
                assert "Python" in text
                assert "pyproject.toml" in text

    asyncio.run(run())
