from pathlib import Path

from repopilot.config import append_readable_root, load_config


def test_explicit_relative_config_path_resolves_from_cwd(tmp_path: Path, monkeypatch) -> None:
    work = tmp_path / "work"
    runtime_home = tmp_path / "runtime-home"
    work.mkdir()
    runtime_home.mkdir()
    config_path = work / "custom.yaml"
    config_path.write_text(
        """
permissions:
  readable_roots:
    - .
  writable_roots:
    - ./outputs
""",
        encoding="utf-8",
    )

    monkeypatch.chdir(work)
    monkeypatch.setenv("REPOPILOT_HOME", str(runtime_home))

    config = load_config("custom.yaml")

    assert config.config_path == config_path.resolve()
    assert config.permissions.writable_roots == [str((work / "outputs").resolve())]


def test_relative_repopilot_config_env_resolves_from_cwd(tmp_path: Path, monkeypatch) -> None:
    work = tmp_path / "work"
    work.mkdir()
    config_path = work / "env-config.yaml"
    config_path.write_text(
        """
permissions:
  readable_roots:
    - .
  writable_roots:
    - ./reports
""",
        encoding="utf-8",
    )

    monkeypatch.chdir(work)
    monkeypatch.setenv("REPOPILOT_CONFIG", "env-config.yaml")

    config = load_config()

    assert config.config_path == config_path.resolve()
    assert config.permissions.writable_roots == [str((work / "reports").resolve())]


def test_relative_permission_paths_resolve_from_config_file(tmp_path: Path) -> None:
    config_path = tmp_path / "repopilot.yaml"
    config_path.write_text(
        """
permissions:
  readable_roots:
    - ./repos
  writable_roots:
    - ./outputs
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.permissions.readable_roots == [str((tmp_path / "repos").resolve())]
    assert config.permissions.writable_roots == [str((tmp_path / "outputs").resolve())]


def test_append_readable_root_writes_absolute_path_once(tmp_path: Path) -> None:
    config_path = tmp_path / "repopilot.yaml"
    repo = tmp_path / "repos" / "demo"
    repo.mkdir(parents=True)
    config_path.write_text(
        """
permissions:
  readable_roots:
    - ./repos
  writable_roots:
    - ./outputs
""",
        encoding="utf-8",
    )

    append_readable_root(config_path, repo)
    append_readable_root(config_path, repo)
    config = load_config(config_path)

    assert config.permissions.readable_roots.count(str(repo.resolve())) == 1


def test_modes_config_loads_tool_budget_matrix(tmp_path: Path) -> None:
    config_path = tmp_path / "repopilot.yaml"
    config_path.write_text(
        """
permissions:
  readable_roots:
    - ./repos
  writable_roots:
    - ./outputs
modes:
  deep-scan:
    model: deepseek-chat
    max_tool_rounds: 12
    enabled_tools:
      - repo_list_tree
      - repo_symbol_map
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.modes["deep-scan"].model == "deepseek-chat"
    assert config.modes["deep-scan"].max_tool_rounds == 12
    assert "repo_symbol_map" in config.modes["deep-scan"].enabled_tools


def test_ui_config_loads_terminal_preferences(tmp_path: Path) -> None:
    config_path = tmp_path / "repopilot.yaml"
    config_path.write_text(
        """
permissions:
  readable_roots:
    - .
  writable_roots:
    - ./outputs
ui:
  animations: false
  show_user_turns: false
  keep_progress_log: true
  logo: none
  compact_width: 100
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.ui.animations is False
    assert config.ui.show_user_turns is False
    assert config.ui.keep_progress_log is True
    assert config.ui.logo == "none"
    assert config.ui.compact_width == 100
