from pathlib import Path

import pytest

from repopilot.config import AppConfig, LimitSettings, PermissionSettings
from repopilot.permissions import PathGuard, PermissionErrorDetail


def make_config(root: Path, out: Path) -> AppConfig:
    return AppConfig(
        permissions=PermissionSettings(
            readable_roots=[str(root)],
            writable_roots=[str(out)],
            deny_patterns=["**/.env", "**/.git/**"],
        ),
        limits=LimitSettings(max_file_chars=20),
        project_root=root,
    )


def test_session_repo_must_be_under_readable_root(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    repo = allowed / "repo"
    outside = tmp_path / "outside"
    repo.mkdir(parents=True)
    outside.mkdir()
    config = make_config(allowed, allowed / "outputs")

    assert PathGuard(config, repo).session_repo == repo.resolve()
    with pytest.raises(PermissionErrorDetail):
        PathGuard(config, outside)


def test_read_path_cannot_escape_session_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (tmp_path / "secret.txt").write_text("x", encoding="utf-8")
    config = make_config(tmp_path, tmp_path / "outputs")
    guard = PathGuard(config, repo)

    with pytest.raises(PermissionErrorDetail):
        guard.resolve_read_path("../secret.txt")


def test_deny_patterns_are_enforced(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".env").write_text("TOKEN=x", encoding="utf-8")
    (repo / ".git").mkdir()
    config = make_config(tmp_path, tmp_path / "outputs")
    guard = PathGuard(config, repo)

    with pytest.raises(PermissionErrorDetail):
        guard.resolve_read_path(".env")
    with pytest.raises(PermissionErrorDetail):
        guard.resolve_read_path(".git")
