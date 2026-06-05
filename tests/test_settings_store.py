from pathlib import Path
import os
import subprocess
import sys

import pytest

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


def _make_dir_symlink(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"directory symlink unavailable: {exc}")


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


def test_runtime_home_summary_counts_profiles_and_reports(tmp_path: Path, monkeypatch) -> None:
    _redirect_store(monkeypatch, tmp_path)
    repo = tmp_path / "project" / "demo"
    repo.mkdir(parents=True)

    store.ensure_local_settings()
    profile = store.ensure_repo_profile(repo)
    (profile.reports_dir / "overview.md").write_text("# Report\n", encoding="utf-8")
    summary = store.runtime_home_summary()

    assert summary.exists is True
    assert summary.marker_valid is True
    assert summary.config_exists is True
    assert summary.env_exists is True
    assert summary.repo_profiles_count == 1
    assert summary.report_dirs_count == 1
    assert summary.report_files_count == 1


def test_clean_runtime_home_dry_run_does_not_delete(tmp_path: Path, monkeypatch) -> None:
    _redirect_store(monkeypatch, tmp_path)
    store.ensure_local_settings()

    plan = store.clean_runtime_home(dry_run=True)

    assert plan.can_clean is True
    assert (tmp_path / "runtime-home" / "config.yaml").exists()


def test_clean_runtime_home_deletes_valid_home(tmp_path: Path, monkeypatch) -> None:
    _redirect_store(monkeypatch, tmp_path)
    store.ensure_local_settings()

    plan = store.clean_runtime_home(dry_run=False)

    assert plan.can_clean is True
    assert not (tmp_path / "runtime-home").exists()


def test_clean_runtime_home_rejects_invalid_marker(tmp_path: Path, monkeypatch) -> None:
    _redirect_store(monkeypatch, tmp_path)
    home = tmp_path / "runtime-home"
    home.mkdir()
    (home / "home.yaml").write_text("kind: something-else\nversion: 1\n", encoding="utf-8")

    plan = store.runtime_clean_plan()

    assert plan.can_clean is False
    with pytest.raises(ValueError):
        store.clean_runtime_home(dry_run=False)
    assert home.exists()


def test_clean_runtime_home_rejects_dangerous_home(tmp_path: Path, monkeypatch) -> None:
    dangerous = Path(tmp_path.anchor)
    monkeypatch.setattr(store, "PROJECT_ROOT", dangerous)
    monkeypatch.setattr(store, "STORE_DIR", dangerous)
    monkeypatch.setattr(store, "LOCAL_CONFIG_PATH", dangerous / "config.yaml")
    monkeypatch.setattr(store, "LOCAL_ENV_PATH", dangerous / ".env")
    monkeypatch.setattr(store, "REPORTS_DIR", dangerous / "reports")
    monkeypatch.setattr(store, "REPOS_DIR", dangerous / "repos")
    monkeypatch.setattr(store, "HOME_MARKER_PATH", dangerous / "home.yaml")

    plan = store.runtime_clean_plan()

    assert plan.can_clean is False
    assert "危险路径" in plan.reason


def test_runtime_home_summary_does_not_follow_report_symlinks(tmp_path: Path, monkeypatch) -> None:
    _redirect_store(monkeypatch, tmp_path)
    repo = tmp_path / "project" / "demo"
    external = tmp_path / "external"
    repo.mkdir(parents=True)
    external.mkdir()
    (external / "outside.md").write_text("outside\n", encoding="utf-8")

    store.ensure_local_settings()
    profile = store.ensure_repo_profile(repo)
    (profile.reports_dir / "overview.md").write_text("# Report\n", encoding="utf-8")
    _make_dir_symlink(profile.reports_dir / "linked", external)
    summary = store.runtime_home_summary()

    assert summary.report_files_count == 1


def test_clean_runtime_home_rejects_symlink_home(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "target-home"
    link = tmp_path / "runtime-home"
    target.mkdir()
    store.save_yaml_document(target / "home.yaml", {"kind": "repopilot-home", "version": 1})
    _make_dir_symlink(link, target)
    monkeypatch.setattr(store, "PROJECT_ROOT", link)
    monkeypatch.setattr(store, "STORE_DIR", link)
    monkeypatch.setattr(store, "LOCAL_CONFIG_PATH", link / "config.yaml")
    monkeypatch.setattr(store, "LOCAL_ENV_PATH", link / ".env")
    monkeypatch.setattr(store, "REPORTS_DIR", link / "reports")
    monkeypatch.setattr(store, "REPOS_DIR", link / "repos")
    monkeypatch.setattr(store, "HOME_MARKER_PATH", link / "home.yaml")

    plan = store.runtime_clean_plan()

    assert plan.can_clean is False
    assert "符号链接" in plan.reason
    with pytest.raises(ValueError):
        store.clean_runtime_home(dry_run=False)
    assert link.is_symlink()
    assert target.exists()


def test_runtime_home_summary_ignores_non_directory_repos_and_reports(tmp_path: Path, monkeypatch) -> None:
    _redirect_store(monkeypatch, tmp_path)
    store.ensure_local_settings()
    store.REPOS_DIR.rmdir()
    store.REPOS_DIR.write_text("not a directory\n", encoding="utf-8")
    store.REPORTS_DIR.write_text("not a directory\n", encoding="utf-8")

    summary = store.runtime_home_summary()

    assert summary.repo_profiles_count == 0
    assert summary.report_dirs_count == 0
    assert summary.report_files_count == 0


def test_clean_runtime_home_rejects_symlink_marker(tmp_path: Path, monkeypatch) -> None:
    _redirect_store(monkeypatch, tmp_path)
    home = tmp_path / "runtime-home"
    external = tmp_path / "external"
    home.mkdir()
    store.save_yaml_document(external / "home.yaml", {"kind": "repopilot-home", "version": 1})
    try:
        (home / "home.yaml").symlink_to(external / "home.yaml")
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"file symlink unavailable: {exc}")

    plan = store.runtime_clean_plan()

    assert plan.can_clean is False
    with pytest.raises(ValueError):
        store.clean_runtime_home(dry_run=False)
    assert home.exists()
