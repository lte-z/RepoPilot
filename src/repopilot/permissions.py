"""Path permission checks for repository sessions."""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path

from .config import AppConfig


class PermissionErrorDetail(ValueError):
    """Raised when a requested path violates RepoPilot permissions."""


def normalize_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def _as_posix(path: Path) -> str:
    return path.as_posix().lower()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


class PathGuard:
    """Validate readable and writable paths for a session repository."""

    def __init__(self, config: AppConfig, session_repo: str | Path, *, validate_session: bool = True):
        self.config = config
        self.session_repo = normalize_path(session_repo)
        self.readable_roots = [normalize_path(root) for root in config.permissions.readable_roots]
        self.writable_roots = [normalize_path(root) for root in config.permissions.writable_roots]
        if validate_session:
            self._validate_session_repo()

    def _validate_session_repo(self) -> None:
        if not self.session_repo.exists():
            raise PermissionErrorDetail(f"仓库路径不存在：{self.session_repo}")
        if not self.session_repo.is_dir():
            raise PermissionErrorDetail(f"仓库路径不是目录：{self.session_repo}")
        if self.config.permissions.allow_all_roots:
            return
        if not any(_is_relative_to(self.session_repo, root) for root in self.readable_roots):
            roots = ", ".join(str(root) for root in self.readable_roots) or "<empty>"
            raise PermissionErrorDetail(
                f"仓库路径不在 readable_roots 白名单内：{self.session_repo}；允许根：{roots}"
            )

    def _check_denied(self, path: Path) -> None:
        rel = path
        try:
            rel = path.relative_to(self.session_repo)
        except ValueError:
            pass
        candidates = [_as_posix(path), _as_posix(rel)]
        for pattern in self.config.permissions.deny_patterns:
            normalized = pattern.replace("\\", "/").lower()
            patterns = [normalized]
            if normalized.endswith("/**"):
                patterns.append(normalized[:-3])
            for candidate in candidates:
                for item in patterns:
                    if fnmatch(candidate, item) or fnmatch("/" + candidate, item):
                        raise PermissionErrorDetail(f"路径被 deny_patterns 拒绝：{path} 匹配 {pattern}")

    def resolve_read_path(self, path: str | Path = ".") -> Path:
        requested = Path(path).expanduser()
        if not requested.is_absolute():
            requested = self.session_repo / requested
        resolved = requested.resolve()
        if not _is_relative_to(resolved, self.session_repo):
            raise PermissionErrorDetail(f"读取路径越过 session repo 边界：{resolved}")
        self._check_denied(resolved)
        return resolved

    def resolve_write_path(self, path: str | Path) -> Path:
        requested = Path(path).expanduser()
        if not requested.is_absolute():
            if not self.writable_roots:
                raise PermissionErrorDetail("未配置 writable_roots，无法解析相对写入路径。")
            requested = self.writable_roots[0] / requested
        resolved = requested.resolve()
        if not any(_is_relative_to(resolved, root) for root in self.writable_roots):
            roots = ", ".join(str(root) for root in self.writable_roots) or "<empty>"
            raise PermissionErrorDetail(
                f"写入路径不在 writable_roots 白名单内：{resolved}；允许根：{roots}"
            )
        self._check_denied(resolved)
        return resolved

    def is_writable_artifact(self, path: str | Path) -> bool:
        resolved = normalize_path(path)
        return any(_is_relative_to(resolved, root) for root in self.writable_roots)

    def relative(self, path: Path) -> str:
        try:
            return path.relative_to(self.session_repo).as_posix()
        except ValueError:
            return path.as_posix()
