"""Local project settings store for RepoPilot."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(os.getenv("REPOPILOT_PROJECT_ROOT", Path.cwd())).expanduser().resolve()
STORE_DIR = PROJECT_ROOT / ".repopilot"
LOCAL_CONFIG_PATH = STORE_DIR / "config.yaml"
LOCAL_ENV_PATH = STORE_DIR / ".env"
REPORTS_DIR = STORE_DIR / "reports"

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
class SettingsHealth:
    store_dir: Path
    config_path: Path
    env_path: Path
    config_exists: bool
    env_exists: bool
    has_api_key: bool
    readable_roots_count: int
    reports_dir: Path


def ensure_store() -> Path:
    """Create the ignored local settings directories."""

    for path in (STORE_DIR, REPORTS_DIR):
        path.mkdir(parents=True, exist_ok=True)
    return STORE_DIR


def _read_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"配置文件格式错误，应为 YAML mapping：{path}")
    return data


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def default_config_data() -> dict[str, Any]:
    """Return a fresh local config document."""

    return {
        "permissions": {
            "allow_all_roots": False,
            "respect_git_ignore": True,
            "readable_roots": [".."],
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
    """Create local ignored config and env files if they do not exist."""

    ensure_store()
    if not LOCAL_CONFIG_PATH.exists():
        data = default_config_data()
        permissions = data.setdefault("permissions", {})
        if isinstance(permissions, dict):
            permissions["readable_roots"] = permissions.get("readable_roots") or [".."]
            permissions["writable_roots"] = ["./reports"]
        _write_yaml(LOCAL_CONFIG_PATH, data)
    if not LOCAL_ENV_PATH.exists():
        write_env_file(LOCAL_ENV_PATH, default_env_data())
    return LOCAL_CONFIG_PATH, LOCAL_ENV_PATH


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
    values = {**default_env_data(), **read_env_file(LOCAL_ENV_PATH)}
    values[key] = value
    write_env_file(LOCAL_ENV_PATH, values)
    return LOCAL_ENV_PATH


def local_config_data() -> dict[str, Any]:
    ensure_local_settings()
    return _read_yaml(LOCAL_CONFIG_PATH)


def save_local_config_data(data: dict[str, Any]) -> Path:
    ensure_store()
    _write_yaml(LOCAL_CONFIG_PATH, data)
    return LOCAL_CONFIG_PATH


def select_config_document(config_path: str | Path | None = None) -> tuple[Path, dict[str, Any]]:
    if config_path is None:
        ensure_local_settings()
        selected = LOCAL_CONFIG_PATH
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


def add_readable_root(root: str | Path) -> Path:
    data = local_config_data()
    roots = _path_list(data, "readable_roots")
    absolute = str(Path(root).expanduser().resolve())
    existing = {
        str((LOCAL_CONFIG_PATH.parent / str(item)).expanduser().resolve())
        if not Path(str(item)).expanduser().is_absolute()
        else str(Path(str(item)).expanduser().resolve())
        for item in roots
    }
    if absolute not in existing:
        roots.append(absolute)
    return save_local_config_data(data)


def remove_readable_root(root: str | Path) -> Path:
    data = local_config_data()
    roots = _path_list(data, "readable_roots")
    absolute = str(Path(root).expanduser().resolve())
    roots[:] = [
        item
        for item in roots
        if (
            str((LOCAL_CONFIG_PATH.parent / str(item)).expanduser().resolve())
            if not Path(str(item)).expanduser().is_absolute()
            else str(Path(str(item)).expanduser().resolve())
        )
        != absolute
    ]
    return save_local_config_data(data)


def set_network_enabled(enabled: bool, config_path: str | Path | None = None) -> Path:
    if config_path is None:
        data = local_config_data()
        selected = LOCAL_CONFIG_PATH
    else:
        selected = Path(config_path).expanduser().resolve()
        data = _read_yaml(selected)
    network = data.setdefault("network", {})
    if not isinstance(network, dict):
        raise ValueError("配置文件中的 network 必须是 YAML mapping。")
    network["allow_http_fetch"] = enabled
    _write_yaml(selected, data)
    return selected


def settings_health(config_path: Path | None = None) -> SettingsHealth:
    ensure_store()
    selected_config = config_path or LOCAL_CONFIG_PATH
    env_values = read_env_file(LOCAL_ENV_PATH)
    readable_roots_count = 0
    if selected_config.exists():
        data = _read_yaml(selected_config)
        permissions = data.get("permissions", {})
        if isinstance(permissions, dict) and isinstance(permissions.get("readable_roots"), list):
            readable_roots_count = len(permissions["readable_roots"])
    return SettingsHealth(
        store_dir=STORE_DIR,
        config_path=selected_config,
        env_path=LOCAL_ENV_PATH,
        config_exists=selected_config.exists(),
        env_exists=LOCAL_ENV_PATH.exists(),
        has_api_key=bool(env_values.get("LLM_API_KEY")),
        readable_roots_count=readable_roots_count,
        reports_dir=REPORTS_DIR,
    )
