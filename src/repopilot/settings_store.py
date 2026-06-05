"""Runtime settings store for RepoPilot."""

from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


HOME_ENV = "REPOPILOT_HOME"
LEGACY_PROJECT_ROOT_ENV = "REPOPILOT_PROJECT_ROOT"


def _platform_default_home() -> Path:
    system = platform.system().lower()
    if system == "windows":
        base = os.getenv("APPDATA") or os.getenv("LOCALAPPDATA")
        if base:
            return Path(base) / "RepoPilot"
        return Path.home() / "AppData" / "Roaming" / "RepoPilot"
    if system == "darwin":
        return Path.home() / "Library" / "Application Support" / "RepoPilot"
    base = os.getenv("XDG_CONFIG_HOME")
    return (Path(base) if base else Path.home() / ".config") / "repopilot"


def _absolute_without_resolving_symlinks(path: str | Path) -> Path:
    return Path(os.path.abspath(Path(path).expanduser()))


def _resolve_runtime_home() -> Path:
    explicit = os.getenv(HOME_ENV)
    if explicit:
        return _absolute_without_resolving_symlinks(explicit)
    legacy = os.getenv(LEGACY_PROJECT_ROOT_ENV)
    if legacy:
        return _absolute_without_resolving_symlinks(Path(legacy).expanduser() / ".repopilot")
    return _absolute_without_resolving_symlinks(_platform_default_home())


PROJECT_ROOT = _resolve_runtime_home()
STORE_DIR = PROJECT_ROOT
LOCAL_CONFIG_PATH = STORE_DIR / "config.yaml"
LOCAL_ENV_PATH = STORE_DIR / ".env"
REPORTS_DIR = STORE_DIR / "reports"
REPOS_DIR = STORE_DIR / "repos"
HOME_MARKER_PATH = STORE_DIR / "home.yaml"

DEFAULT_FALLBACK_IGNORE_PATTERNS = [
    "**/.next/**",
    "**/.nuxt/**",
    "**/.parcel-cache/**",
    "**/.svelte-kit/**",
    "**/.turbo/**",
    "**/.vs/**",
    "**/build/**",
    "**/coverage/**",
    "**/debug/**",
    "**/dist/**",
    "**/*.egg-info/**",
    "**/.mypy_cache/**",
    "**/node_modules/**",
    "**/out/**",
    "**/.pytest_cache/**",
    "**/.ruff_cache/**",
    "**/release/**",
    "**/target/**",
    "**/__pycache__/**",
]


@dataclass(frozen=True)
class RuntimePaths:
    home: Path
    config_path: Path
    env_path: Path
    reports_dir: Path
    repos_dir: Path
    marker_path: Path


@dataclass(frozen=True)
class RepoProfile:
    repo_id: str
    repo_path: Path
    profile_dir: Path
    profile_path: Path
    reports_dir: Path


@dataclass(frozen=True)
class SettingsHealth:
    store_dir: Path
    config_path: Path
    env_path: Path
    config_exists: bool
    env_exists: bool
    has_api_key: bool
    readable_roots_count: int
    reports_dir: Path


@dataclass(frozen=True)
class RuntimeHomeSummary:
    home: Path
    exists: bool
    marker_path: Path
    marker_exists: bool
    marker_valid: bool
    config_path: Path
    env_path: Path
    config_exists: bool
    env_exists: bool
    repos_dir: Path
    repo_profiles_count: int
    report_dirs_count: int
    report_files_count: int
    total_files_count: int


@dataclass(frozen=True)
class RuntimeCleanPlan:
    home: Path
    exists: bool
    can_clean: bool
    reason: str
    entries: list[Path]


def runtime_paths() -> RuntimePaths:
    return RuntimePaths(
        home=STORE_DIR,
        config_path=LOCAL_CONFIG_PATH,
        env_path=LOCAL_ENV_PATH,
        reports_dir=REPORTS_DIR,
        repos_dir=REPOS_DIR,
        marker_path=HOME_MARKER_PATH,
    )


def _home_marker_data() -> dict[str, Any]:
    return {"kind": "repopilot-home", "version": 1}


def ensure_store() -> Path:
    """Create the RepoPilot runtime home directories."""

    paths = runtime_paths()
    for path in (paths.home, paths.repos_dir):
        path.mkdir(parents=True, exist_ok=True)
    if not paths.marker_path.exists():
        _write_yaml(paths.marker_path, _home_marker_data())
    return paths.home


def _read_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"配置文件格式错误，应为 YAML mapping：{path}")
    return data


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def default_config_data() -> dict[str, Any]:
    """Return a fresh runtime config document."""

    return {
        "permissions": {
            "allow_all_roots": False,
            "respect_git_ignore": True,
            "readable_roots": [str(Path.cwd().resolve())],
            "writable_roots": ["./reports"],
            "deny_patterns": ["**/.env", "**/.env.*", "**/.git/**", "**/.venv/**"],
            "fallback_ignore_patterns": list(DEFAULT_FALLBACK_IGNORE_PATTERNS),
        },
        "execution": {"allow_command_execution": False, "allowed_commands": []},
        "intent": {
            "use_llm_router": True,
            "fallback_to_rules": True,
            "min_confidence": 0.55,
            "max_prompt_context_chars": 2500,
        },
        "network": {
            "allow_http_fetch": True,
            "allowed_domains": [],
            "deny_private_hosts": True,
            "timeout_seconds": 15,
            "max_fetch_chars": 20000,
        },
        "ui": {
            "animations": True,
            "show_user_turns": True,
            "keep_progress_log": False,
            "logo": "compact",
            "compact_width": 92,
        },
        "limits": {
            "max_file_chars": 20000,
            "max_search_results": 50,
            "max_tree_entries": 300,
            "max_tool_rounds": 8,
            "llm_timeout_seconds": 120,
            "tool_timeout_seconds": 60,
            "intent_timeout_seconds": 15,
            "max_context_artifacts": 3,
            "max_repeated_tool_calls": 1,
        },
        "modes": {
            "overview": {
                "model": None,
                "max_tool_rounds": 6,
                "enabled_tools": [
                    "repo_list_tree",
                    "repo_detect_stack",
                    "repo_git_summary",
                    "repo_read_file",
                    "web_fetch_url",
                ],
            },
            "runbook": {
                "model": None,
                "max_tool_rounds": 6,
                "enabled_tools": [
                    "repo_list_tree",
                    "repo_detect_stack",
                    "repo_read_file",
                    "repo_search_text",
                    "web_fetch_url",
                ],
            },
            "module-map": {
                "model": None,
                "max_tool_rounds": 7,
                "enabled_tools": [
                    "repo_list_tree",
                    "repo_detect_stack",
                    "repo_read_file",
                    "repo_search_text",
                    "repo_symbol_map",
                ],
            },
            "task-brief": {
                "model": None,
                "max_tool_rounds": 5,
                "enabled_tools": [
                    "repo_search_text",
                    "repo_read_file",
                    "repo_symbol_map",
                ],
            },
            "deep-scan": {
                "model": None,
                "max_tool_rounds": 10,
                "enabled_tools": [
                    "repo_list_tree",
                    "repo_detect_stack",
                    "repo_git_summary",
                    "repo_read_file",
                    "repo_search_text",
                    "repo_symbol_map",
                    "web_fetch_url",
                ],
            },
        },
    }


def default_env_data() -> dict[str, str]:
    return {
        "LLM_PROVIDER": "",
        "LLM_BASE_URL": "",
        "LLM_API_KEY": "",
        "LLM_MODEL": "",
    }


def ensure_local_settings() -> tuple[Path, Path]:
    """Create RepoPilot home config and env files if they do not exist."""

    paths = runtime_paths()
    ensure_store()
    if not paths.config_path.exists():
        _write_yaml(paths.config_path, default_config_data())
    if not paths.env_path.exists():
        write_env_file(paths.env_path, default_env_data())
    return paths.config_path, paths.env_path


def _safe_repo_name(repo_path: Path) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", repo_path.name).strip("-")
    return name or "repo"


def repo_profile_id(repo_path: str | Path) -> str:
    resolved = Path(repo_path).expanduser().resolve()
    digest = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:12]
    return f"{_safe_repo_name(resolved)}-{digest}"


def repo_profile(repo_path: str | Path) -> RepoProfile:
    resolved = Path(repo_path).expanduser().resolve()
    repo_id = repo_profile_id(resolved)
    profile_dir = runtime_paths().repos_dir / repo_id
    return RepoProfile(
        repo_id=repo_id,
        repo_path=resolved,
        profile_dir=profile_dir,
        profile_path=profile_dir / "profile.yaml",
        reports_dir=profile_dir / "reports",
    )


def ensure_repo_profile(repo_path: str | Path) -> RepoProfile:
    profile = repo_profile(repo_path)
    now = time.time()
    profile.reports_dir.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any]
    if profile.profile_path.exists():
        data = _read_yaml(profile.profile_path)
        data["last_used_at"] = now
    else:
        data = {
            "repo_id": profile.repo_id,
            "repo_path": str(profile.repo_path),
            "reports_dir": str(profile.reports_dir),
            "created_at": now,
            "last_used_at": now,
        }
    _write_yaml(profile.profile_path, data)
    return profile


def load_yaml_document(path: Path) -> dict[str, Any]:
    return _read_yaml(path)


def save_yaml_document(path: Path, data: dict[str, Any]) -> None:
    _write_yaml(path, data)


def read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def write_env_file(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    order = ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL")
    lines = [f"{key}={values.get(key, '')}" for key in order]
    extra = sorted(key for key in values if key not in order)
    lines.extend(f"{key}={values[key]}" for key in extra)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def update_env_value(key: str, value: str) -> Path:
    ensure_local_settings()
    paths = runtime_paths()
    values = {**default_env_data(), **read_env_file(paths.env_path)}
    values[key] = value
    write_env_file(paths.env_path, values)
    return paths.env_path


def local_config_data() -> dict[str, Any]:
    ensure_local_settings()
    return _read_yaml(runtime_paths().config_path)


def save_local_config_data(data: dict[str, Any]) -> Path:
    paths = runtime_paths()
    ensure_store()
    _write_yaml(paths.config_path, data)
    return paths.config_path


def select_config_document(config_path: str | Path | None = None) -> tuple[Path, dict[str, Any]]:
    if config_path is None:
        ensure_local_settings()
        selected = runtime_paths().config_path
    else:
        selected = Path(config_path).expanduser().resolve()
    return selected, _read_yaml(selected)


def get_config_value(key: str, config_path: str | Path | None = None) -> Any:
    _, data = select_config_document(config_path)
    current: Any = data
    default_current: Any = default_config_data()
    for part in key.split("."):
        if not isinstance(default_current, dict) or part not in default_current:
            raise KeyError(f"未知配置项：{key}")
        default_current = default_current[part]
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            current = default_current
    return current


def _parse_config_value(raw: str) -> Any:
    try:
        return yaml.safe_load(raw)
    except yaml.YAMLError:
        return raw


def set_config_value(key: str, raw_value: str, config_path: str | Path | None = None) -> Path:
    selected, data = select_config_document(config_path)
    parts = key.split(".")
    if not parts or any(not part for part in parts):
        raise KeyError(f"未知配置项：{key}")
    current: Any = data
    defaults = default_config_data()
    default_current: Any = defaults
    for part in parts[:-1]:
        if not isinstance(default_current, dict) or part not in default_current:
            raise KeyError(f"未知配置项：{key}")
        if not isinstance(current, dict):
            raise KeyError(f"未知配置项：{key}")
        if part not in current:
            current[part] = {}
        current = current[part]
        default_current = default_current.get(part, {}) if isinstance(default_current, dict) else {}
    leaf = parts[-1]
    if not isinstance(default_current, dict) or leaf not in default_current:
        raise KeyError(f"未知配置项：{key}")
    if not isinstance(current, dict):
        raise KeyError(f"未知配置项：{key}")
    current[leaf] = _parse_config_value(raw_value)
    _write_yaml(selected, data)
    return selected


def reset_config_value(key: str, config_path: str | Path | None = None) -> Path:
    selected, data = select_config_document(config_path)
    defaults = default_config_data()
    current: Any = data
    default_current: Any = defaults
    parts = key.split(".")
    for part in parts[:-1]:
        if not isinstance(default_current, dict) or part not in default_current:
            raise KeyError(f"该配置项没有默认值：{key}")
        if not isinstance(current, dict):
            raise KeyError(f"未知配置项：{key}")
        if part not in current:
            current[part] = {}
        current = current[part]
        default_current = default_current[part]
    leaf = parts[-1]
    if not isinstance(default_current, dict) or leaf not in default_current:
        raise KeyError(f"该配置项没有默认值：{key}")
    if not isinstance(current, dict):
        raise KeyError(f"未知配置项：{key}")
    current[leaf] = default_current[leaf]
    _write_yaml(selected, data)
    return selected


def flatten_config(data: dict[str, Any] | None = None, prefix: str = "") -> dict[str, Any]:
    source = data if data is not None else local_config_data()
    flattened: dict[str, Any] = {}
    for key, value in source.items():
        dotted = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            flattened.update(flatten_config(value, dotted))
        else:
            flattened[dotted] = value
    return flattened


def merge_with_defaults(data: dict[str, Any]) -> dict[str, Any]:
    def merge(default: Any, current: Any) -> Any:
        if isinstance(default, dict):
            merged = dict(default)
            if isinstance(current, dict):
                for key, value in current.items():
                    merged[key] = merge(default.get(key), value)
            return merged
        return current if current is not None else default

    return merge(default_config_data(), data)


def _path_list(data: dict[str, Any], key: str) -> list[Any]:
    permissions = data.setdefault("permissions", {})
    if not isinstance(permissions, dict):
        raise ValueError("配置文件中的 permissions 必须是 YAML mapping。")
    values = permissions.setdefault(key, [])
    if not isinstance(values, list):
        raise ValueError(f"配置文件中的 permissions.{key} 必须是列表。")
    return values


def _resolve_config_relative(value: Any) -> str:
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return str(path.resolve())
    return str((runtime_paths().config_path.parent / path).resolve())


def add_readable_root(root: str | Path) -> Path:
    data = local_config_data()
    roots = _path_list(data, "readable_roots")
    absolute = str(Path(root).expanduser().resolve())
    existing = {_resolve_config_relative(item) for item in roots}
    if absolute not in existing:
        roots.append(absolute)
    return save_local_config_data(data)


def remove_readable_root(root: str | Path) -> Path:
    data = local_config_data()
    roots = _path_list(data, "readable_roots")
    absolute = str(Path(root).expanduser().resolve())
    roots[:] = [item for item in roots if _resolve_config_relative(item) != absolute]
    return save_local_config_data(data)


def set_network_enabled(enabled: bool, config_path: str | Path | None = None) -> Path:
    if config_path is None:
        data = local_config_data()
        selected = runtime_paths().config_path
    else:
        selected = Path(config_path).expanduser().resolve()
        data = _read_yaml(selected)
    network = data.setdefault("network", {})
    if not isinstance(network, dict):
        raise ValueError("配置文件中的 network 必须是 YAML mapping。")
    network["allow_http_fetch"] = enabled
    _write_yaml(selected, data)
    return selected


def _marker_is_valid(path: Path) -> bool:
    if not path.exists() or path.is_symlink() or not path.is_file():
        return False
    try:
        data = _read_yaml(path)
    except (OSError, ValueError, yaml.YAMLError):
        return False
    expected = _home_marker_data()
    return data.get("kind") == expected["kind"] and data.get("version") == expected["version"]


def _count_runtime_files(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return 1
    count = 0
    for _, _, files in os.walk(path, followlinks=False):
        count += len(files)
    return count


def runtime_home_summary() -> RuntimeHomeSummary:
    """Return a read-only summary of the current RepoPilot home."""

    paths = runtime_paths()
    repo_profiles_count = 0
    report_dirs_count = 0
    report_files_count = 0
    if paths.repos_dir.is_dir() and not paths.repos_dir.is_symlink():
        repo_profiles_count = sum(1 for item in paths.repos_dir.glob("*/profile.yaml") if item.is_file())
        report_dirs = [item for item in paths.repos_dir.glob("*/reports") if item.is_dir() and not item.is_symlink()]
        report_dirs_count = len(report_dirs)
        report_files_count = sum(_count_runtime_files(report_dir) for report_dir in report_dirs)
    if paths.reports_dir.is_dir() and not paths.reports_dir.is_symlink():
        report_dirs_count += 1
        report_files_count += _count_runtime_files(paths.reports_dir)
    return RuntimeHomeSummary(
        home=paths.home,
        exists=paths.home.exists(),
        marker_path=paths.marker_path,
        marker_exists=paths.marker_path.exists(),
        marker_valid=_marker_is_valid(paths.marker_path),
        config_path=paths.config_path,
        env_path=paths.env_path,
        config_exists=paths.config_path.exists(),
        env_exists=paths.env_path.exists(),
        repos_dir=paths.repos_dir,
        repo_profiles_count=repo_profiles_count,
        report_dirs_count=report_dirs_count,
        report_files_count=report_files_count,
        total_files_count=_count_runtime_files(paths.home),
    )


def _is_dangerous_cleanup_target(path: Path) -> bool:
    resolved = _absolute_without_resolving_symlinks(path)
    if resolved.parent == resolved:
        return True
    try:
        if resolved == _absolute_without_resolving_symlinks(Path.home()):
            return True
    except RuntimeError:
        pass
    return len(resolved.parts) <= 1


def runtime_clean_plan() -> RuntimeCleanPlan:
    """Validate and describe the cleanup target without deleting anything."""

    paths = runtime_paths()
    home = _absolute_without_resolving_symlinks(paths.home)
    marker_path = home / "home.yaml"
    if home.is_symlink():
        return RuntimeCleanPlan(home=home, exists=True, can_clean=False, reason="RepoPilot home 是符号链接，拒绝自动删除。", entries=[])
    if _is_dangerous_cleanup_target(home):
        return RuntimeCleanPlan(home=home, exists=home.exists(), can_clean=False, reason="拒绝清理危险路径。", entries=[])
    if not home.exists():
        return RuntimeCleanPlan(home=home, exists=False, can_clean=True, reason="RepoPilot home 不存在，无需清理。", entries=[])
    if not home.is_dir():
        return RuntimeCleanPlan(home=home, exists=True, can_clean=False, reason="RepoPilot home 不是目录。", entries=[])
    if not _marker_is_valid(marker_path):
        return RuntimeCleanPlan(
            home=home,
            exists=True,
            can_clean=False,
            reason="缺少合法 RepoPilot home marker，拒绝自动删除。",
            entries=[],
        )
    entries = sorted(home.iterdir(), key=lambda item: item.name.lower())
    return RuntimeCleanPlan(home=home, exists=True, can_clean=True, reason="将删除整个 RepoPilot home。", entries=entries)


def clean_runtime_home(dry_run: bool = False) -> RuntimeCleanPlan:
    """Delete the current RepoPilot home after marker-based validation."""

    plan = runtime_clean_plan()
    if dry_run or not plan.exists:
        return plan
    if not plan.can_clean:
        raise ValueError(plan.reason)
    shutil.rmtree(plan.home)
    return plan


def settings_health(config_path: Path | None = None) -> SettingsHealth:
    paths = runtime_paths()
    ensure_store()
    selected_config = config_path or paths.config_path
    env_values = read_env_file(paths.env_path)
    readable_roots_count = 0
    if selected_config.exists():
        data = _read_yaml(selected_config)
        permissions = data.get("permissions", {})
        if isinstance(permissions, dict) and isinstance(permissions.get("readable_roots"), list):
            readable_roots_count = len(permissions["readable_roots"])
    return SettingsHealth(
        store_dir=paths.home,
        config_path=selected_config,
        env_path=paths.env_path,
        config_exists=selected_config.exists(),
        env_exists=paths.env_path.exists(),
        has_api_key=bool(env_values.get("LLM_API_KEY")),
        readable_roots_count=readable_roots_count,
        reports_dir=paths.reports_dir,
    )
