from pathlib import Path
import os
import subprocess
import sys

import repopilot.settings_store as store


def _redirect_store(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "project"
    local = tmp_path / "runtime-home"
    root.mkdir()
    monkeypatch.setattr(store, "PROJECT_ROOT", local)
    monkeypatch.setattr(store, "STORE_DIR", local)
    monkeypatch.setattr(store, "LOCAL_CONFIG_PATH", local / "config.yaml")
    monkeypatch.setattr(store, "LOCAL_ENV_PATH", local / ".env")
    monkeypatch.setattr(store, "REPORTS_DIR", local / "reports")
    monkeypatch.setattr(store, "REPOS_DIR", local / "repos")
    monkeypatch.setattr(store, "HOME_MARKER_PATH", local / "home.yaml")


def test_ensure_local_settings_creates_runtime_home(tmp_path: Path, monkeypatch) -> None:
    _redirect_store(monkeypatch, tmp_path)

    config_path, env_path = store.ensure_local_settings()

    assert config_path == tmp_path / "runtime-home" / "config.yaml"
    assert env_path == tmp_path / "runtime-home" / ".env"
    assert not (tmp_path / "runtime-home" / "reports").exists()
    assert (tmp_path / "runtime-home" / "repos").is_dir()
    assert (tmp_path / "runtime-home" / "home.yaml").exists()
    assert not (tmp_path / "project" / ".repopilot").exists()
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


def test_repo_profile_is_stored_under_runtime_home(tmp_path: Path, monkeypatch) -> None:
    _redirect_store(monkeypatch, tmp_path)
    first = tmp_path / "workspace-a" / "demo"
    second = tmp_path / "workspace-b" / "demo"
    first.mkdir(parents=True)
    second.mkdir(parents=True)

    first_profile = store.ensure_repo_profile(first)
    second_profile = store.ensure_repo_profile(second)

    assert first_profile.repo_id != second_profile.repo_id
    assert first_profile.profile_dir.parent == tmp_path / "runtime-home" / "repos"
    assert first_profile.reports_dir.is_dir()
    assert first_profile.profile_path.exists()
    data = store.load_yaml_document(first_profile.profile_path)
    assert data["repo_path"] == str(first.resolve())
    assert data["reports_dir"] == str(first_profile.reports_dir)
    assert not (first / ".repopilot").exists()


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


def test_setup_uses_repopilot_home_without_polluting_cwd(tmp_path: Path) -> None:
    project = tmp_path / "relocated-project"
    home = tmp_path / "runtime-home"
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
        env={**os.environ, "PYTHONPATH": str(src_root), "REPOPILOT_HOME": str(home)},
        capture_output=True,
        text=True,
        check=True,
    )

    assert str(home / "config.yaml") in result.stdout
    assert (home / "config.yaml").exists()
    assert (home / ".env").exists()
    assert not (project / ".repopilot").exists()
