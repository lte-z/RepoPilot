from pathlib import Path
import os
import subprocess
import sys

import repopilot.settings_store as store


def _redirect_store(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "project"
    local = root / ".repopilot"
    root.mkdir()
    monkeypatch.setattr(store, "PROJECT_ROOT", root)
    monkeypatch.setattr(store, "STORE_DIR", local)
    monkeypatch.setattr(store, "LOCAL_CONFIG_PATH", local / "config.yaml")
    monkeypatch.setattr(store, "LOCAL_ENV_PATH", local / ".env")
    monkeypatch.setattr(store, "REPORTS_DIR", local / "reports")


def test_ensure_local_settings_creates_ignored_runtime_store(tmp_path: Path, monkeypatch) -> None:
    _redirect_store(monkeypatch, tmp_path)

    config_path, env_path = store.ensure_local_settings()

    assert config_path == tmp_path / "project" / ".repopilot" / "config.yaml"
    assert env_path == tmp_path / "project" / ".repopilot" / ".env"
    assert (tmp_path / "project" / ".repopilot" / "reports").is_dir()
    assert not (tmp_path / "project" / ".repopilot" / "sessions").exists()
    assert not (tmp_path / "project" / ".repopilot" / "cache").exists()
    assert "LLM_API_KEY=" in env_path.read_text(encoding="utf-8")
    data = store.load_yaml_document(config_path)
    assert data["intent"]["use_llm_router"] is True
    assert data["intent"]["fallback_to_rules"] is True
    assert data["ui"]["animations"] is True
    assert data["ui"]["show_user_turns"] is True
    assert data["ui"]["keep_progress_log"] is False
    assert "**/node_modules/**" in data["permissions"]["fallback_ignore_patterns"]
    assert "**/build/**" in data["permissions"]["fallback_ignore_patterns"]
    assert "deep-scan" in data["modes"]
    assert "repo_symbol_map" in data["modes"]["module-map"]["enabled_tools"]


def test_add_and_remove_readable_root_resolves_relative_roots_from_store(tmp_path: Path, monkeypatch) -> None:
    _redirect_store(monkeypatch, tmp_path)
    repo = tmp_path / "project" / "demo"
    repo.mkdir()

    store.ensure_local_settings()
    store.add_readable_root(repo)
    store.add_readable_root(repo)
    data = store.local_config_data()

    roots = data["permissions"]["readable_roots"]
    assert roots.count(str(repo.resolve())) == 1

    store.remove_readable_root(repo)
    data = store.local_config_data()
    assert str(repo.resolve()) not in data["permissions"]["readable_roots"]


def test_update_env_value_preserves_blank_provider_defaults(tmp_path: Path, monkeypatch) -> None:
    _redirect_store(monkeypatch, tmp_path)

    store.update_env_value("LLM_MODEL", "deepseek-chat")
    values = store.read_env_file(store.LOCAL_ENV_PATH)

    assert values["LLM_PROVIDER"] == ""
    assert values["LLM_BASE_URL"] == ""
    assert values["LLM_MODEL"] == "deepseek-chat"


def test_set_and_get_intent_config_value(tmp_path: Path, monkeypatch) -> None:
    _redirect_store(monkeypatch, tmp_path)
    store.ensure_local_settings()

    store.set_config_value("intent.min_confidence", "0.7")

    assert store.get_config_value("intent.min_confidence") == 0.7


def test_setup_uses_current_working_directory_for_runtime_store(tmp_path: Path) -> None:
    project = tmp_path / "relocated-project"
    project.mkdir()
    src_root = Path(__file__).resolve().parents[1] / "src"

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from repopilot.settings_store import ensure_local_settings; "
            "print(ensure_local_settings()[0])",
        ],
        cwd=project,
        env={**os.environ, "PYTHONPATH": str(src_root)},
        capture_output=True,
        text=True,
        check=True,
    )

    assert str(project / ".repopilot" / "config.yaml") in result.stdout
    assert (project / ".repopilot" / "config.yaml").exists()
