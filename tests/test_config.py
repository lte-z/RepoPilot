from pathlib import Path

from repopilot.config import append_readable_root, load_config


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
