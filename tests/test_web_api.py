from pathlib import Path

from fastapi.testclient import TestClient

import repopilot.settings_store as store

from repopilot.web import app


def _redirect_runtime_home(monkeypatch, home: Path) -> None:
    monkeypatch.setattr(store, "PROJECT_ROOT", home)
    monkeypatch.setattr(store, "STORE_DIR", home)
    monkeypatch.setattr(store, "LOCAL_CONFIG_PATH", home / "config.yaml")
    monkeypatch.setattr(store, "LOCAL_ENV_PATH", home / ".env")
    monkeypatch.setattr(store, "REPORTS_DIR", home / "reports")
    monkeypatch.setattr(store, "REPOS_DIR", home / "repos")
    monkeypatch.setattr(store, "HOME_MARKER_PATH", home / "home.yaml")


def test_web_api_analyze_offline_reuses_agent_core(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    outputs = tmp_path / "outputs"
    repo.mkdir()
    outputs.mkdir()
    _redirect_runtime_home(monkeypatch, tmp_path / "runtime-home")
    (repo / "pyproject.toml").write_text("[project]\nname = 'sample'\n", encoding="utf-8")
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
    monkeypatch.setenv("REPOPILOT_CONFIG", str(config_path))

    client = TestClient(app)
    response = client.post(
        "/api/analyze",
        json={"repo_path": str(repo), "mode": "overview", "offline": True, "save": True},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["offline"] is True
    assert data["mode"] == "overview"
    assert "## 结论" in data["markdown"]
    assert [call["name"] for call in data["tool_calls"]] == [
        "repo_list_tree",
        "repo_detect_stack",
        "repo_git_summary",
    ]
    assert not (outputs / "repo-overview.md").exists()
    reports = list((tmp_path / "runtime-home" / "repos").glob("*/reports/repo-overview.md"))
    assert len(reports) == 1

    report = client.get("/api/reports/repo-overview.md")
    assert report.status_code == 200
    assert "## 结论" in report.text


def test_web_api_rejects_unknown_mode(tmp_path: Path, monkeypatch) -> None:
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
    monkeypatch.setenv("REPOPILOT_CONFIG", str(config_path))

    client = TestClient(app)
    response = client.post(
        "/api/analyze",
        json={"repo_path": str(repo), "mode": "unknown", "offline": True},
    )

    assert response.status_code == 422


def test_web_api_task_brief_requires_task(tmp_path: Path, monkeypatch) -> None:
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
    monkeypatch.setenv("REPOPILOT_CONFIG", str(config_path))

    client = TestClient(app)
    response = client.post(
        "/api/analyze",
        json={"repo_path": str(repo), "mode": "task-brief", "offline": True},
    )

    assert response.status_code == 400
    assert "需要提供任务文本" in response.json()["detail"]
