"""Configuration loading for RepoPilot."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from .settings_store import (
    LOCAL_CONFIG_PATH,
    PROJECT_ROOT,
    DEFAULT_FALLBACK_IGNORE_PATTERNS,
    ensure_local_settings,
    read_env_file,
    runtime_paths,
)

DEFAULT_CONFIG_PATH = LOCAL_CONFIG_PATH


class PermissionSettings(BaseModel):
    allow_all_roots: bool = False
    respect_git_ignore: bool = True
    readable_roots: list[str] = Field(default_factory=list)
    writable_roots: list[str] = Field(default_factory=list)
    deny_patterns: list[str] = Field(default_factory=list)
    fallback_ignore_patterns: list[str] = Field(default_factory=lambda: list(DEFAULT_FALLBACK_IGNORE_PATTERNS))


class ExecutionSettings(BaseModel):
    allow_command_execution: bool = False
    allowed_commands: list[str] = Field(default_factory=list)


class IntentSettings(BaseModel):
    use_llm_router: bool = True
    fallback_to_rules: bool = True
    min_confidence: float = 0.55
    max_prompt_context_chars: int = 2500


class ModeSettings(BaseModel):
    model: str | None = None
    max_tool_rounds: int | None = None
    enabled_tools: list[str] = Field(default_factory=list)


class LimitSettings(BaseModel):
    max_file_chars: int = 20_000
    max_search_results: int = 50
    max_tree_entries: int = 300
    max_tool_rounds: int = 8
    llm_timeout_seconds: float = 120
    tool_timeout_seconds: float = 60
    intent_timeout_seconds: float = 15
    max_context_artifacts: int = 3
    max_repeated_tool_calls: int = 1


class LLMSettings(BaseModel):
    provider: str = ""
    base_url: str = ""
    api_key: str = ""
    model: str = ""


class NetworkSettings(BaseModel):
    allow_http_fetch: bool = True
    allowed_domains: list[str] = Field(default_factory=list)
    deny_private_hosts: bool = True
    timeout_seconds: float = 15
    max_fetch_chars: int = 20_000


class UISettings(BaseModel):
    animations: bool = True
    show_user_turns: bool = True
    keep_progress_log: bool = False
    logo: str = "compact"
    compact_width: int = 92


class AppConfig(BaseModel):
    permissions: PermissionSettings = Field(default_factory=PermissionSettings)
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)
    intent: IntentSettings = Field(default_factory=IntentSettings)
    limits: LimitSettings = Field(default_factory=LimitSettings)
    network: NetworkSettings = Field(default_factory=NetworkSettings)
    ui: UISettings = Field(default_factory=UISettings)
    modes: dict[str, ModeSettings] = Field(default_factory=dict)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    config_path: Path = DEFAULT_CONFIG_PATH
    project_root: Path = PROJECT_ROOT


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在：{path}")
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        raise ValueError(f"配置文件格式错误，应为 YAML mapping：{path}")
    return data


def _resolve_path(value: str, base_dir: Path) -> str:
    path = Path(value).expanduser()
    if path.is_absolute():
        return str(path.resolve())
    return str((base_dir / path).resolve())


def _resolve_permission_paths(data: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    permissions = data.get("permissions")
    if not isinstance(permissions, dict):
        return data
    resolved = dict(permissions)
    for key in ("readable_roots", "writable_roots"):
        values = resolved.get(key, [])
        if isinstance(values, list):
            resolved[key] = [_resolve_path(str(value), base_dir) for value in values]
    return {**data, "permissions": resolved}


def _select_config_path(config_path: str | Path | None = None) -> Path:
    selected_value = config_path if config_path is not None else os.getenv("REPOPILOT_CONFIG")
    if selected_value:
        selected = Path(selected_value).expanduser()
        if not selected.is_absolute():
            selected = (Path.cwd() / selected).resolve()
        return selected
    selected, _ = ensure_local_settings()
    return selected.resolve()


def _load_llm_settings() -> LLMSettings:
    values = read_env_file(runtime_paths().env_path)

    def pick(key: str, default: str = "") -> str:
        return values.get(key) or os.getenv(key, default)

    return LLMSettings(
        provider=pick("LLM_PROVIDER", ""),
        base_url=pick("LLM_BASE_URL", ""),
        api_key=pick("LLM_API_KEY", ""),
        model=pick("LLM_MODEL", ""),
    )


def load_config(config_path: str | Path | None = None) -> AppConfig:
    """Load RepoPilot configuration and environment variables."""

    selected = _select_config_path(config_path)
    data = _load_yaml(selected)
    data = _resolve_permission_paths(data, selected.parent)
    data.pop("llm", None)
    data.pop("config_path", None)
    data.pop("project_root", None)
    llm = _load_llm_settings()
    return AppConfig(**data, llm=llm, config_path=selected.resolve(), project_root=runtime_paths().home)


def with_report_dir(config: AppConfig, reports_dir: str | Path) -> AppConfig:
    """Return a config copy whose write boundary is a specific reports directory."""

    resolved = Path(reports_dir).expanduser().resolve()
    permissions = config.permissions.model_copy(update={"writable_roots": [str(resolved)]})
    return config.model_copy(update={"permissions": permissions, "project_root": resolved})


def append_readable_root(config_path: str | Path | None, root: str | Path) -> Path:
    """Append an absolute readable root to the selected local YAML config."""

    selected = _select_config_path(config_path)
    data = _load_yaml(selected)
    permissions = data.setdefault("permissions", {})
    if not isinstance(permissions, dict):
        raise ValueError("配置文件中的 permissions 必须是 YAML mapping。")
    readable_roots = permissions.setdefault("readable_roots", [])
    if not isinstance(readable_roots, list):
        raise ValueError("配置文件中的 permissions.readable_roots 必须是列表。")

    absolute = str(Path(root).expanduser().resolve())
    existing = {_resolve_path(str(item), selected.parent) for item in readable_roots}
    if absolute not in existing:
        readable_roots.append(absolute)
        with selected.open("w", encoding="utf-8") as file:
            yaml.safe_dump(data, file, allow_unicode=True, sort_keys=False)
    return selected.resolve()
