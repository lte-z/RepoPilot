from pathlib import Path
import os
import subprocess
import sys
import json

import yaml
from typer.testing import CliRunner

import repopilot.cli as cli
from repopilot.cli import app
from repopilot.config import AppConfig, LLMSettings


runner = CliRunner()


def _write_config(tmp_path: Path) -> Path:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
permissions:
  readable_roots:
    - {tmp_path.as_posix()}
  writable_roots:
    - {outputs.as_posix()}
  deny_patterns:
    - "**/.env"
    - "**/.git/**"
execution:
  allow_command_execution: false
  allowed_commands: []
network:
  allow_http_fetch: false
limits:
  max_file_chars: 20000
  max_search_results: 20
  max_tree_entries: 80
  max_tool_rounds: 4
""",
        encoding="utf-8",
    )
    return config_path


def test_cli_mcp_shows_network_tool_state(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)

    result = runner.invoke(app, ["mcp", "--config", str(config_path)])

    assert result.exit_code == 0
    assert "repo_list_tree" in result.stdout
    assert "web_fetch_url" in result.stdout
    assert "off" in result.stdout


def test_cli_mcp_can_toggle_explicit_config(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)

    result = runner.invoke(app, ["mcp", "on", "--config", str(config_path)])

    assert result.exit_code == 0
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["network"]["allow_http_fetch"] is True


def test_cli_config_get_set_reset_explicit_config(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)

    set_result = runner.invoke(app, ["config", "set", "limits.max_tool_rounds", "12", "--config", str(config_path)])
    get_result = runner.invoke(app, ["config", "get", "limits.max_tool_rounds", "--config", str(config_path)])
    reset_result = runner.invoke(app, ["config", "reset", "limits.max_tool_rounds", "--config", str(config_path)])

    assert set_result.exit_code == 0
    assert get_result.exit_code == 0
    assert "limits.max_tool_rounds = 12" in get_result.stdout
    assert reset_result.exit_code == 0
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["limits"]["max_tool_rounds"] == 8


def test_cli_overview_offline_runs_with_explicit_config(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("demo", encoding="utf-8")
    config_path = _write_config(tmp_path)

    result = runner.invoke(app, ["overview", str(repo), "--config", str(config_path), "--offline"])

    assert result.exit_code == 0
    assert "Report / overview" in result.stdout
    assert "repo_list_tree" in result.stdout


def test_cli_deep_scan_offline_runs_with_explicit_config(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("def entrypoint():\n    return True\n", encoding="utf-8")
    config_path = _write_config(tmp_path)

    result = runner.invoke(app, ["deep-scan", str(repo), "--config", str(config_path), "--offline"])

    assert result.exit_code == 0
    assert "Report / deep-scan" in result.stdout
    assert "repo_symbol_map" in result.stdout


def test_cli_overview_json_output_is_machine_readable(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("demo", encoding="utf-8")
    config_path = _write_config(tmp_path)

    result = runner.invoke(app, ["overview", str(repo), "--config", str(config_path), "--offline", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["mode"] == "overview"
    assert data["offline"] is True
    assert any(call["name"] == "repo_list_tree" for call in data["tool_calls"])


def test_cli_chat_help_and_exit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config_path = _write_config(tmp_path)

    result = runner.invoke(
        app,
        ["chat", str(repo), "--config", str(config_path), "--offline"],
        input="/help\n/exit\n",
    )

    assert result.exit_code == 0
    assert "/overview" in result.stdout
    assert "RepoPilot Chat" in result.stdout


def test_cli_chat_quick_action_prints_progress(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("demo", encoding="utf-8")
    config_path = _write_config(tmp_path)

    result = runner.invoke(
        app,
        ["chat", str(repo), "--config", str(config_path), "--offline"],
        input="/overview\n/exit\n",
    )

    assert result.exit_code == 0
    assert "生成仓库概览" in result.stdout
    assert "使用离线模式调用本地工具" in result.stdout
    assert "RepoPilot" in result.stdout


def test_cli_chat_rejects_compound_help_command(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config_path = _write_config(tmp_path)

    result = runner.invoke(
        app,
        ["chat", str(repo), "--config", str(config_path), "--offline"],
        input="/help 你还有什么其他功能吗？\n/exit\n",
    )

    assert result.exit_code == 0
    assert "只接受这些分组" in result.stdout
    assert "使用离线模式调用本地工具" not in result.stdout


def test_cli_chat_settings_can_update_config(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config_path = _write_config(tmp_path)

    result = runner.invoke(
        app,
        ["chat", str(repo), "--config", str(config_path), "--offline"],
        input="/settings set limits.max_tool_rounds 12\n/settings get limits.max_tool_rounds\n/exit\n",
    )

    assert result.exit_code == 0
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["limits"]["max_tool_rounds"] == 12
    assert "limits.max_tool_rounds = 12" in result.stdout


def test_cli_chat_mcp_command_updates_session_config(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config_path = _write_config(tmp_path)

    result = runner.invoke(
        app,
        ["chat", str(repo), "--config", str(config_path), "--offline"],
        input="/mcp on\n/exit\n",
    )

    assert result.exit_code == 0
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["network"]["allow_http_fetch"] is True


def test_cli_chat_sources_tools_and_artifacts_are_tabular(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("demo", encoding="utf-8")
    config_path = _write_config(tmp_path)

    result = runner.invoke(
        app,
        ["chat", str(repo), "--config", str(config_path), "--offline"],
        input="/overview\n/sources\n/tools\n/artifacts\n/exit\n",
    )

    assert result.exit_code == 0
    assert "Sources" in result.stdout
    assert "Tools" in result.stdout
    assert "Artifacts" in result.stdout
    assert "repo_list_tree" in result.stdout


def test_cli_chat_clear_requires_confirmation_and_reprints_dashboard(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config_path = _write_config(tmp_path)

    result = runner.invoke(
        app,
        ["chat", str(repo), "--config", str(config_path), "--offline"],
        input="/clear\ny\n/exit\n",
    )

    assert result.exit_code == 0
    assert "确认清空当前会话上下文并清屏" in result.stdout
    assert "Quick Actions" in result.stdout


def test_cli_default_entry_guides_user_into_chat(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    calls: list[tuple[str, bool]] = []

    monkeypatch.setattr(cli, "ensure_local_settings", lambda: (tmp_path / "config.yaml", tmp_path / ".env"))
    monkeypatch.setattr(cli, "load_config", lambda *args, **kwargs: AppConfig(llm=LLMSettings(api_key="")))
    monkeypatch.setattr(
        cli,
        "_start_chat",
        lambda repo_path, config_path, offline, clear_screen=True: calls.append((repo_path, offline)),
    )

    result = runner.invoke(app, [], input=f"n\n{repo}\n")

    assert result.exit_code == 0
    assert calls == [(str(repo), True)]
    assert "RepoPilot" in result.stdout


def test_provider_presets_cover_common_openai_compatible_services() -> None:
    aliases = list(cli.PROVIDER_PRESETS)

    assert aliases[:3] == ["openai", "gemini", "deepseek"]
    assert "qwen" in aliases
    assert "kimi" in aliases
    assert "openrouter" in aliases
    assert cli.PROVIDER_PRESETS["gemini"][1] == "https://generativelanguage.googleapis.com/v1beta/openai/"
    assert cli.PROVIDER_PRESETS["qwen"][1] == "https://dashscope.aliyuncs.com/compatible-mode/v1"


def test_cli_setup_uses_invocation_cwd_for_runtime_store(tmp_path: Path) -> None:
    project = tmp_path / "relocated-project"
    project.mkdir()
    src_root = Path(__file__).resolve().parents[1] / "src"

    result = subprocess.run(
        [sys.executable, "-m", "repopilot.cli", "setup", "--skip-api-key"],
        cwd=project,
        env={**os.environ, "PYTHONPATH": str(src_root)},
        capture_output=True,
        text=True,
        check=True,
    )

    assert ".repopilot" in result.stdout
    assert (project / ".repopilot" / "config.yaml").exists()
    assert (project / ".repopilot" / ".env").exists()


def test_cli_setup_can_use_provider_preset(tmp_path: Path) -> None:
    project = tmp_path / "provider-project"
    project.mkdir()
    src_root = Path(__file__).resolve().parents[1] / "src"

    subprocess.run(
        [sys.executable, "-m", "repopilot.cli", "setup", "--skip-api-key", "--provider", "gemini"],
        cwd=project,
        env={**os.environ, "PYTHONPATH": str(src_root)},
        capture_output=True,
        text=True,
        check=True,
    )

    env_text = (project / ".repopilot" / ".env").read_text(encoding="utf-8")
    assert "LLM_PROVIDER=Google Gemini" in env_text
    assert "LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/" in env_text
    assert "LLM_MODEL=gemini-2.5-flash" in env_text
