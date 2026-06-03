from pathlib import Path

from repopilot.agent import run_analysis
from repopilot.config import AppConfig, LimitSettings, PermissionSettings


def test_offline_task_brief_uses_multiple_task_queries(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "auth.py").write_text("def login_flow():\n    pass\n", encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    config = AppConfig(
        permissions=PermissionSettings(
            readable_roots=[str(tmp_path)],
            writable_roots=[str(tmp_path / "outputs")],
            deny_patterns=["**/.env", "**/.git/**", "**/__pycache__/**"],
        ),
        limits=LimitSettings(max_search_results=5),
    )
    config_path.write_text(config.model_dump_json(), encoding="utf-8")

    result = run_analysis("task-brief", str(repo), "分析 login_flow 登录流程", config_path=config_path, offline=True)

    search_calls = [call for call in result.tool_calls if call.name == "repo_search_text"]
    assert len(search_calls) >= 2
    assert "任务相关搜索" in result.markdown


def test_task_brief_requires_task_text(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
permissions:
  readable_roots:
    - {tmp_path.as_posix()}
  writable_roots:
    - {(tmp_path / "outputs").as_posix()}
  deny_patterns: []
""",
        encoding="utf-8",
    )

    try:
        run_analysis("task-brief", str(repo), config_path=config_path, offline=True)
    except ValueError as exc:
        assert "需要提供任务文本" in str(exc)
    else:
        raise AssertionError("task-brief should require task text")


def test_offline_analysis_reports_progress(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("hello", encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
permissions:
  readable_roots:
    - {tmp_path.as_posix()}
  writable_roots:
    - {(tmp_path / "outputs").as_posix()}
  deny_patterns: []
""",
        encoding="utf-8",
    )
    events: list[str] = []

    run_analysis("overview", str(repo), config_path=config_path, offline=True, progress=events.append)

    assert any("离线模式" in event for event in events)
