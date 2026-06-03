"""Configuration loading for RepoPilot."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.example.yaml"


class PermissionSettings(BaseModel):
    allow_all_roots: bool = False
    respect_git_ignore: bool = True
    readable_roots: list[str] = Field(default_factory=list)
    writable_roots: list[str] = Field(default_factory=list)
    deny_patterns: list[str] = Field(default_factory=list)
    fallback_ignore_patterns: list[str] = Field(default_factory=lambda: [
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
    ])


class ExecutionSettings(BaseModel):
    allow_command_execution: bool = False
    allowed_commands: list[str] = Field(default_factory=list)


class LimitSettings(BaseModel):
    max_file_chars: int = 20_000
    max_search_results: int = 50
    max_tree_entries: int = 300
    max_tool_rounds: int = 8
    llm_timeout_seconds: float = 120
    tool_timeout_seconds: float = 60


class LLMSettings(BaseModel):
    base_url: str = "https://api.deepseek.com"
    api_key: str = ""
    model: str = "deepseek-v4-flash"


class NetworkSettings(BaseModel):
    allow_http_fetch: bool = True
    allowed_domains: list[str] = Field(default_factory=list)
    deny_private_hosts: bool = True
    timeout_seconds: float = 15
    max_fetch_chars: int = 20_000


class AppConfig(BaseModel):
    permissions: PermissionSettings = Field(default_factory=PermissionSettings)
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)
    limits: LimitSettings = Field(default_factory=LimitSettings)
    network: NetworkSettings = Field(default_factory=NetworkSettings)
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
    selected = Path(
        config_path
        or os.getenv("REPOPILOT_CONFIG")
        or DEFAULT_CONFIG_PATH
    ).expanduser()
    if not selected.is_absolute():
        selected = (PROJECT_ROOT / selected).resolve()
    return selected


def load_config(config_path: str | Path | None = None) -> AppConfig:
    """Load RepoPilot configuration and environment variables."""

    load_dotenv(PROJECT_ROOT / ".env")
    selected = _select_config_path(config_path)
    data = _load_yaml(selected)
    data = _resolve_permission_paths(data, selected.parent)
    data.pop("llm", None)
    data.pop("config_path", None)
    data.pop("project_root", None)
    llm = LLMSettings(
        base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
        api_key=os.getenv("LLM_API_KEY", ""),
        model=os.getenv("LLM_MODEL", "deepseek-v4-flash"),
    )
    return AppConfig(**data, llm=llm, config_path=selected.resolve())


def append_readable_root(config_path: str | Path | None, root: str | Path) -> Path:
    """Append an absolute readable root to the selected local YAML config."""

    selected = _select_config_path(config_path)
    if selected.resolve() == DEFAULT_CONFIG_PATH.resolve():
        raise ValueError("当前使用的是 config.example.yaml，请先创建本地 config.yaml 后再持久授权。")

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
