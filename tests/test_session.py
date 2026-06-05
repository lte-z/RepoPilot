from pathlib import Path

from repopilot.intent import IntentDecision
import repopilot.settings_store as store
import repopilot.session as session_module
from repopilot.session import ChatSession, _normalize_report_markdown


def _redirect_runtime_home(monkeypatch, home: Path) -> None:
    monkeypatch.setattr(store, "PROJECT_ROOT", home)
    monkeypatch.setattr(store, "STORE_DIR", home)
    monkeypatch.setattr(store, "LOCAL_CONFIG_PATH", home / "config.yaml")
    monkeypatch.setattr(store, "LOCAL_ENV_PATH", home / ".env")
    monkeypatch.setattr(store, "REPORTS_DIR", home / "reports")
    monkeypatch.setattr(store, "REPOS_DIR", home / "repos")
    monkeypatch.setattr(store, "HOME_MARKER_PATH", home / "home.yaml")


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


def test_chat_session_runs_quick_action_and_tracks_artifacts(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    config_path = _write_config(tmp_path)

    session = ChatSession(str(repo), config_path=config_path, offline=True)
    artifact = session.run_quick_action("overview")

    assert artifact.mode == "overview"
    assert "## 结论" in artifact.markdown
    assert session.state.artifacts == [artifact]
    assert [event.name for event in session.state.tool_events] == [
        "repo_list_tree",
        "repo_detect_stack",
        "repo_git_summary",
    ]


def test_chat_session_follow_up_uses_context_and_can_save(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "auth.py").write_text("def login_flow():\n    return True\n", encoding="utf-8")
    config_path = _write_config(tmp_path)
    _redirect_runtime_home(monkeypatch, tmp_path / "runtime-home")

    session = ChatSession(str(repo), config_path=config_path, offline=True)
    session.run_quick_action("overview")
    follow_up = session.send_message("login_flow 在哪里？")
    saved = session.save_artifact()

    assert follow_up.mode == "task-brief"
    assert "任务相关搜索" in follow_up.markdown
    assert "报告已保存" in saved
    assert not any((tmp_path / "outputs").glob("repo-task-brief-*.md"))
    assert any((tmp_path / "runtime-home" / "repos").glob("*/reports/repo-task-brief-*.md"))


def test_saved_chat_report_is_normalized_as_standalone_markdown() -> None:
    markdown = """---

## 仓库概览：Demo

### 结论

正文

### 证据

更多正文
"""

    normalized = _normalize_report_markdown("Demo - 仓库概览", markdown)

    assert normalized.startswith("# 仓库概览：Demo\n\n## 结论")
    assert "\n## 证据" in normalized
    assert not normalized.startswith("---")


def test_chat_session_mcp_status_reflects_network_switch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config_path = _write_config(tmp_path)

    session = ChatSession(str(repo), config_path=config_path, offline=True)
    status = session.get_mcp_status()

    assert status.connected is True
    assert status.network_enabled is False
    assert "web_fetch_url" not in status.tools


def test_chat_session_meta_question_does_not_call_tools(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config_path = _write_config(tmp_path)

    session = ChatSession(str(repo), config_path=config_path, offline=True)
    artifact = session.send_message("你还能做什么？")

    assert artifact.mode == "chat"
    assert "我能做什么" in artifact.markdown
    assert session.state.tool_events == []


def test_chat_session_context_explanation_does_not_rescan_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("demo", encoding="utf-8")
    config_path = _write_config(tmp_path)

    session = ChatSession(str(repo), config_path=config_path, offline=True)
    session.run_quick_action("overview")
    tool_count = len(session.state.tool_events)
    artifact = session.send_message("解释一下刚才的结论")

    assert artifact.mode == "chat"
    assert "基于当前上下文" in artifact.markdown
    assert len(session.state.tool_events) == tool_count


def test_chat_session_repo_request_routes_to_overview(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("demo", encoding="utf-8")
    config_path = _write_config(tmp_path)

    session = ChatSession(str(repo), config_path=config_path, offline=True)
    artifact = session.send_message("分析这个仓库")

    assert artifact.mode == "overview"
    assert artifact.title == "repo - 仓库概览"
    assert any(event.name == "repo_list_tree" for event in session.state.tool_events)


def test_chat_session_natural_language_analysis_titles_match_modes(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("demo", encoding="utf-8")
    config_path = _write_config(tmp_path)
    decisions = iter(
        [
            IntentDecision(
                intent="repo_runbook",
                confidence=0.9,
                needs_tools=True,
                mode="runbook",
                reason="runbook",
                source="llm",
            ),
            IntentDecision(
                intent="repo_module_map",
                confidence=0.9,
                needs_tools=True,
                mode="module-map",
                reason="module map",
                source="llm",
            ),
            IntentDecision(
                intent="repo_task_brief",
                confidence=0.9,
                needs_tools=True,
                mode="task-brief",
                task="定位登录流程",
                reason="task brief",
                source="llm",
            ),
            IntentDecision(
                intent="repo_deep_scan",
                confidence=0.9,
                needs_tools=True,
                mode="deep-scan",
                reason="deep scan",
                source="llm",
            ),
        ]
    )

    monkeypatch.setattr(session_module, "run_intent_router", lambda *args, **kwargs: next(decisions))

    session = ChatSession(str(repo), config_path=config_path, offline=True)
    runbook = session.send_message("怎么运行")
    module_map = session.send_message("模块结构")
    task_brief = session.send_message("定位登录流程")
    deep_scan = session.send_message("完整入职包")

    assert runbook.title == "repo - 运行手册"
    assert module_map.title == "repo - 模块地图"
    assert task_brief.title == "repo - 任务简报"
    assert deep_scan.title == "repo - 仓库入职包"


def test_chat_session_uses_intent_router_for_meta_help(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config_path = _write_config(tmp_path)

    monkeypatch.setattr(
        session_module,
        "run_intent_router",
        lambda *args, **kwargs: IntentDecision(
            intent="meta_help",
            confidence=0.98,
            needs_tools=False,
            reply_strategy="answer_capabilities",
            reason="能力询问",
            source="llm",
        ),
    )

    session = ChatSession(str(repo), config_path=config_path, offline=False)
    artifact = session.send_message("你还有别的能力吗？")

    assert artifact.mode == "chat"
    assert "我能做什么" in artifact.markdown
    assert session.state.tool_events == []


def test_chat_session_uses_intent_router_for_repo_overview(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("demo", encoding="utf-8")
    config_path = _write_config(tmp_path)

    monkeypatch.setattr(
        session_module,
        "run_intent_router",
        lambda *args, **kwargs: IntentDecision(
            intent="repo_overview",
            confidence=0.92,
            needs_tools=True,
            mode="overview",
            reply_strategy="run_overview",
            reason="请求整体分析",
            source="llm",
        ),
    )

    session = ChatSession(str(repo), config_path=config_path, offline=True)
    artifact = session.send_message("帮我看看这个项目")

    assert artifact.mode == "overview"
    assert any(event.name == "repo_detect_stack" for event in session.state.tool_events)
