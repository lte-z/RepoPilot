"""Repository inspection tools shared by MCP, CLI, and WebUI."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tomllib
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from repopilot.config import AppConfig, load_config
from repopilot.permissions import PathGuard


ResponseFormat = Literal["markdown", "json"]


class RepoPathInput(BaseModel):
    repo_path: str = Field(description="Absolute path of the session repository.")


class ListTreeInput(RepoPathInput):
    path: str = Field(default=".", description="Directory path relative to repo_path.")
    max_depth: int = Field(default=3, ge=0, le=8, description="Maximum directory depth.")
    max_entries: int | None = Field(default=None, ge=1, description="Maximum entries to return.")
    response_format: ResponseFormat = "markdown"


class ReadFileInput(RepoPathInput):
    path: str = Field(description="File path relative to repo_path.")
    max_chars: int | None = Field(default=None, ge=1, description="Maximum characters to read.")
    response_format: ResponseFormat = "markdown"


class SearchTextInput(RepoPathInput):
    query: str = Field(description="Text or regular expression to search.")
    glob: str | None = Field(default=None, description="Optional rg glob filter, for example '*.py'.")
    max_results: int | None = Field(default=None, ge=1, description="Maximum matches to return.")
    response_format: ResponseFormat = "markdown"


class DetectStackInput(RepoPathInput):
    response_format: ResponseFormat = "markdown"


class GitSummaryInput(RepoPathInput):
    max_commits: int = Field(default=5, ge=1, le=20, description="Maximum recent commits to include.")
    response_format: ResponseFormat = "markdown"


class SaveReportInput(BaseModel):
    filename: str = Field(description="Report filename under outputs/.")
    content: str = Field(description="Markdown report content.")
    response_format: ResponseFormat = "markdown"


def _format(data: dict[str, Any], markdown: str, response_format: ResponseFormat) -> str:
    if response_format == "json":
        return json.dumps(data, ensure_ascii=False, indent=2)
    return markdown


def _guard(repo_path: str, config: AppConfig | None = None) -> PathGuard:
    return PathGuard(config or load_config(), repo_path)


def _is_probably_binary(path: Path) -> bool:
    with path.open("rb") as file:
        sample = file.read(4096)
    return b"\x00" in sample


def _matches_any_pattern(rel: str, patterns: list[str]) -> bool:
    normalized = rel.replace("\\", "/").lower()
    candidates = [normalized, "/" + normalized]
    for pattern in patterns:
        item = pattern.replace("\\", "/").lower()
        variants = [item]
        if item.endswith("/**"):
            variants.append(item[:-3])
        for candidate in candidates:
            if fnmatch(candidate, item) or any(fnmatch(candidate, variant) for variant in variants):
                return True
    return False


def _matches_fallback_ignore(path: Path, guard: PathGuard) -> bool:
    try:
        rel = path.relative_to(guard.session_repo).as_posix()
    except ValueError:
        return False
    return _matches_any_pattern(rel, guard.config.permissions.fallback_ignore_patterns)


def _git(args: list[str], repo: Path, *, timeout: int = 20) -> tuple[int, str, str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def _is_git_repository(guard: PathGuard) -> bool:
    try:
        code, inside, _ = _git(["rev-parse", "--is-inside-work-tree"], guard.session_repo, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return code == 0 and inside == "true"


def _git_visible_files(guard: PathGuard) -> list[Path]:
    if not guard.config.permissions.respect_git_ignore or not _is_git_repository(guard):
        return []
    try:
        code, stdout, _ = _git(["ls-files", "-co", "--exclude-standard", "-z"], guard.session_repo, timeout=20)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if code != 0 or not stdout:
        return []

    files: list[Path] = []
    writable_rel_roots: list[str] = []
    for root in guard.writable_roots:
        try:
            writable_rel_roots.append(root.relative_to(guard.session_repo).as_posix().lower())
        except ValueError:
            continue
    for item in stdout.split("\0"):
        if not item:
            continue
        rel = Path(item)
        if rel.is_absolute() or ".." in rel.parts:
            continue
        rel_text = rel.as_posix()
        if _matches_any_pattern(rel_text, guard.config.permissions.deny_patterns):
            continue
        if any(rel_text.lower() == root or rel_text.lower().startswith(root + "/") for root in writable_rel_roots):
            continue
        files.append(guard.session_repo / item)
    return files


def _is_ignored(path: Path, guard: PathGuard) -> bool:
    try:
        rel = path.relative_to(guard.session_repo).as_posix()
    except ValueError:
        return False
    if guard.config.permissions.respect_git_ignore and _is_git_repository(guard):
        try:
            code, _, _ = _git(["check-ignore", "-q", "--", rel], guard.session_repo, timeout=5)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            code = 1
        return code == 0
    return _matches_fallback_ignore(path, guard)


def _iter_readable_files(guard: PathGuard, *, max_depth: int | None = None):
    git_files = _git_visible_files(guard)
    if git_files:
        for path in git_files:
            if max_depth is not None:
                try:
                    rel_depth = len(path.relative_to(guard.session_repo).parts)
                except ValueError:
                    continue
                if rel_depth > max_depth:
                    continue
            yield path
        return

    for root, dirs, files in os.walk(guard.session_repo):
        root_path = Path(root)
        allowed_dirs = []
        for dirname in dirs:
            directory = root_path / dirname
            if guard.is_writable_artifact(directory) or _matches_fallback_ignore(directory, guard):
                continue
            try:
                guard.resolve_read_path(directory)
            except ValueError:
                continue
            if max_depth is not None:
                try:
                    rel_depth = len(directory.relative_to(guard.session_repo).parts)
                except ValueError:
                    continue
                if rel_depth >= max_depth:
                    continue
            allowed_dirs.append(dirname)
        dirs[:] = allowed_dirs
        for filename in files:
            path = root_path / filename
            if guard.is_writable_artifact(path) or _matches_fallback_ignore(path, guard):
                continue
            try:
                guard.resolve_read_path(path)
            except ValueError:
                continue
            if max_depth is not None:
                try:
                    rel_depth = len(path.relative_to(guard.session_repo).parts)
                except ValueError:
                    continue
                if rel_depth > max_depth:
                    continue
            yield path


def _writable_glob_excludes(guard: PathGuard) -> list[str]:
    excludes: list[str] = []
    for root in guard.writable_roots:
        try:
            rel = root.relative_to(guard.session_repo).as_posix()
        except ValueError:
            continue
        excludes.extend([f"!{rel}", f"!{rel}/**"])
    return excludes


def _fallback_glob_excludes(guard: PathGuard) -> list[str]:
    return ["!" + pattern.replace("\\", "/") for pattern in guard.config.permissions.fallback_ignore_patterns]


def _fallback_search(params: SearchTextInput, guard: PathGuard, max_results: int) -> tuple[list[dict[str, Any]], bool]:
    try:
        pattern = re.compile(params.query)
    except re.error:
        pattern = re.compile(re.escape(params.query))

    results: list[dict[str, Any]] = []
    truncated = False
    for path in _iter_readable_files(guard):
        rel = guard.relative(path)
        if params.glob and not (fnmatch(rel, params.glob) or fnmatch(path.name, params.glob)):
            continue
        try:
            if _is_probably_binary(path):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            match = pattern.search(line)
            if not match:
                continue
            if len(results) >= max_results:
                truncated = True
                return results, truncated
            results.append(
                {
                    "path": rel,
                    "line": line_number,
                    "column": match.start() + 1,
                    "text": line.strip(),
                }
            )
    return results, truncated


def repo_list_tree(params: ListTreeInput, config: AppConfig | None = None) -> str:
    """List a bounded tree under the session repository."""

    cfg = config or load_config()
    guard = _guard(params.repo_path, cfg)
    root = guard.resolve_read_path(params.path)
    if not root.exists():
        return f"Error: 路径不存在：{root}"
    if not root.is_dir():
        return f"Error: 路径不是目录：{root}"

    max_entries = params.max_entries or cfg.limits.max_tree_entries
    entries: list[dict[str, Any]] = []
    skipped = 0

    git_files = _git_visible_files(guard)
    if git_files:
        seen: set[str] = set()
        for file in sorted(git_files, key=lambda p: guard.relative(p).lower()):
            if len(entries) >= max_entries:
                break
            try:
                rel_to_root = file.relative_to(root)
            except ValueError:
                continue
            parts = rel_to_root.parts
            for index, _ in enumerate(parts, start=1):
                if index > params.max_depth:
                    break
                item_path = root / Path(*parts[:index])
                rel = guard.relative(item_path)
                if rel in seen:
                    continue
                if len(entries) >= max_entries:
                    skipped += 1
                    break
                seen.add(rel)
                entries.append(
                    {
                        "path": rel,
                        "type": "file" if index == len(parts) else "directory",
                        "size": item_path.stat().st_size if item_path.is_file() else None,
                        "depth": index,
                    }
                )
        lines = [f"# 目录树：{guard.relative(root) or '.'}", ""]
        for item in entries:
            indent = "  " * max(item["depth"] - 1, 0)
            suffix = "/" if item["type"] == "directory" else ""
            lines.append(f"{indent}- {item['path']}{suffix}")
        if skipped:
            lines.append(f"\n已达到数量上限，省略 {skipped} 个分支或条目。")
        data = {"root": guard.relative(root), "entries": entries, "truncated": bool(skipped), "source": "git"}
        return _format(data, "\n".join(lines), params.response_format)

    def walk(current: Path, depth: int) -> None:
        nonlocal skipped
        if len(entries) >= max_entries:
            skipped += 1
            return
        if depth > params.max_depth:
            return
        try:
            children = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            return
        for child in children:
            if guard.is_writable_artifact(child) or _matches_fallback_ignore(child, guard):
                continue
            try:
                guard.resolve_read_path(child)
            except ValueError:
                continue
            if len(entries) >= max_entries:
                skipped += 1
                break
            entries.append(
                {
                    "path": guard.relative(child),
                    "type": "directory" if child.is_dir() else "file",
                    "size": child.stat().st_size if child.is_file() else None,
                    "depth": depth,
                }
            )
            if child.is_dir():
                walk(child, depth + 1)

    walk(root, 1)
    lines = [f"# 目录树：{guard.relative(root) or '.'}", ""]
    for item in entries:
        indent = "  " * max(item["depth"] - 1, 0)
        suffix = "/" if item["type"] == "directory" else ""
        lines.append(f"{indent}- {item['path']}{suffix}")
    if skipped:
        lines.append(f"\n已达到数量上限，省略 {skipped} 个分支或条目。")
    data = {"root": guard.relative(root), "entries": entries, "truncated": bool(skipped)}
    return _format(data, "\n".join(lines), params.response_format)


def repo_read_file(params: ReadFileInput, config: AppConfig | None = None) -> str:
    """Read a text file inside the session repository."""

    cfg = config or load_config()
    guard = _guard(params.repo_path, cfg)
    path = guard.resolve_read_path(params.path)
    if not path.exists():
        return f"Error: 文件不存在：{path}"
    if not path.is_file():
        return f"Error: 路径不是文件：{path}"
    if _is_ignored(path, guard):
        return f"Error: 文件被 Git ignore 或 fallback_ignore_patterns 忽略：{guard.relative(path)}"
    if _is_probably_binary(path):
        return f"Error: 拒绝读取疑似二进制文件：{guard.relative(path)}"

    max_chars = params.max_chars or cfg.limits.max_file_chars
    with path.open("r", encoding="utf-8", errors="replace") as file:
        content = file.read(max_chars + 1)
    truncated = len(content) > max_chars
    content = content[:max_chars]
    rel = guard.relative(path)
    markdown = f"# 文件：{rel}\n\n```text\n{content}\n```"
    if truncated:
        markdown += f"\n\n已截断：返回前 {max_chars} 字符。"
    data = {"path": rel, "content": content, "truncated": truncated, "returned_chars": len(content)}
    return _format(data, markdown, params.response_format)


def repo_search_text(params: SearchTextInput, config: AppConfig | None = None) -> str:
    """Search text in the session repository using ripgrep or a local fallback."""

    cfg = config or load_config()
    guard = _guard(params.repo_path, cfg)
    max_results = params.max_results or cfg.limits.max_search_results
    command = [
        "rg",
        "--line-number",
        "--column",
        "--no-heading",
        "--color",
        "never",
        "--max-count",
        "20",
    ]
    for pattern in cfg.permissions.deny_patterns:
        command.extend(["--glob", "!" + pattern.replace("\\", "/")])
    if not (cfg.permissions.respect_git_ignore and _is_git_repository(guard)):
        for pattern in _fallback_glob_excludes(guard):
            command.extend(["--glob", pattern])
    for pattern in _writable_glob_excludes(guard):
        command.extend(["--glob", pattern])
    if params.glob:
        command.extend(["--glob", params.glob])
    command.append("--")
    command.append(params.query)
    used_fallback = False
    try:
        completed = subprocess.run(
            command,
            cwd=str(guard.session_repo),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
    except FileNotFoundError:
        used_fallback = True
        results, truncated = _fallback_search(params, guard, max_results)
    except subprocess.TimeoutExpired:
        return "Error: 搜索超时，请缩小 query 或 glob 范围。"
    else:
        if completed.returncode not in (0, 1):
            return f"Error: rg 搜索失败：{completed.stderr.strip()}"

        results = []
        for line in completed.stdout.splitlines():
            if len(results) >= max_results:
                break
            parts = line.split(":", 3)
            if len(parts) < 4:
                continue
            file_path, line_no, column, text = parts
            try:
                guard.resolve_read_path(file_path)
            except ValueError:
                continue
            results.append(
                {
                    "path": file_path.replace("\\", "/"),
                    "line": int(line_no),
                    "column": int(column),
                    "text": text.strip(),
                }
            )
        truncated = len(completed.stdout.splitlines()) > len(results)

    lines = [f"# 搜索：{params.query}", ""]
    if used_fallback:
        lines.append("未找到 `rg`，已使用内置文本搜索 fallback。")
        lines.append("")
    if not results:
        lines.append("未找到匹配结果。")
    for item in results:
        lines.append(f"- `{item['path']}:{item['line']}:{item['column']}` {item['text']}")
    if truncated:
        lines.append(f"\n已达到结果上限：{max_results}")
    data = {"query": params.query, "results": results, "truncated": truncated, "fallback": used_fallback}
    return _format(data, "\n".join(lines), params.response_format)


def repo_detect_stack(params: DetectStackInput, config: AppConfig | None = None) -> str:
    """Detect common technology stack and project entry clues."""

    guard = _guard(params.repo_path, config)
    markers = {
        "Python": ["pyproject.toml", "requirements.txt", "setup.py", "Pipfile"],
        "Node.js": ["package.json", "pnpm-lock.yaml", "yarn.lock", "package-lock.json"],
        "Rust": ["Cargo.toml"],
        "Go": ["go.mod"],
        "Java": ["pom.xml", "build.gradle", "settings.gradle"],
        "C/C++": ["CMakeLists.txt", "Makefile", "configure.ac"],
        ".NET": ["*.csproj", "*.sln"],
        "Docker": ["Dockerfile", "docker-compose.yml", "compose.yaml"],
    }
    found: dict[str, list[str]] = {}
    all_files = list(_iter_readable_files(guard, max_depth=4))
    for file in all_files:
        rel = guard.relative(file)
        name = file.name
        for stack, patterns in markers.items():
            if stack in found and len(found[stack]) >= 10:
                continue
            for pattern in patterns:
                if fnmatch(name, pattern) or fnmatch(rel, pattern):
                    found.setdefault(stack, []).append(rel)
                    break
    found = {stack: sorted(set(files))[:10] for stack, files in found.items()}

    scripts: dict[str, Any] = {}
    python_project: dict[str, Any] = {}
    pyproject = guard.session_repo / "pyproject.toml"
    if pyproject.exists() and not _is_ignored(pyproject, guard):
        try:
            guard.resolve_read_path(pyproject)
            pyproject_data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            project = pyproject_data.get("project", {})
            tool = pyproject_data.get("tool", {})
            if isinstance(project, dict):
                project_scripts = project.get("scripts", {})
                optional_dependencies = project.get("optional-dependencies", {})
                if isinstance(project_scripts, dict) and project_scripts:
                    python_project["project_scripts"] = project_scripts
                if isinstance(optional_dependencies, dict) and optional_dependencies:
                    python_project["optional_dependencies"] = sorted(optional_dependencies.keys())
            if isinstance(tool, dict):
                tooling = sorted(name for name in ("pytest", "ruff", "mypy", "uv") if name in tool)
                if tooling:
                    python_project["tooling"] = tooling
        except (OSError, tomllib.TOMLDecodeError, ValueError):
            python_project = {"error": "pyproject.toml 无法解析"}

    package_json = guard.session_repo / "package.json"
    if package_json.exists() and not _is_ignored(package_json, guard):
        try:
            guard.resolve_read_path(package_json)
            package_data = json.loads(package_json.read_text(encoding="utf-8"))
            scripts = package_data.get("scripts", {}) if isinstance(package_data, dict) else {}
        except (json.JSONDecodeError, OSError, ValueError):
            scripts = {"error": "package.json 无法解析"}

    lines = ["# 技术栈识别", ""]
    if not found:
        lines.append("未识别到常见技术栈标记文件。")
    for stack, files in found.items():
        lines.append(f"## {stack}")
        for file in files:
            lines.append(f"- `{file}`")
    if scripts:
        lines.extend(["", "## package.json scripts"])
        for name, script in scripts.items():
            lines.append(f"- `{name}`: `{script}`")
    if python_project:
        lines.extend(["", "## Python project clues"])
        project_scripts = python_project.get("project_scripts") if isinstance(python_project, dict) else None
        if isinstance(project_scripts, dict) and project_scripts:
            for name, script in project_scripts.items():
                lines.append(f"- script `{name}`: `{script}`")
        tooling = python_project.get("tooling") if isinstance(python_project, dict) else None
        if isinstance(tooling, list) and tooling:
            lines.append(f"- tooling: {', '.join(f'`{name}`' for name in tooling)}")
        optional = python_project.get("optional_dependencies") if isinstance(python_project, dict) else None
        if isinstance(optional, list) and optional:
            lines.append(f"- optional dependency groups: {', '.join(f'`{name}`' for name in optional)}")
        if "error" in python_project:
            lines.append(f"- {python_project['error']}")
    data = {"stacks": found, "package_scripts": scripts, "python_project": python_project}
    return _format(data, "\n".join(lines), params.response_format)

def repo_git_summary(params: GitSummaryInput, config: AppConfig | None = None) -> str:
    """Return read-only Git metadata for the session repository."""

    guard = _guard(params.repo_path, config)
    code, inside, _ = _git(["rev-parse", "--is-inside-work-tree"], guard.session_repo)
    if code != 0 or inside != "true":
        data = {"is_git_repository": False}
        markdown = "# Git 摘要\n\n该路径不是 Git 仓库，已跳过 Git 摘要。"
        return _format(data, markdown, params.response_format)
    _, branch, _ = _git(["branch", "--show-current"], guard.session_repo)
    _, remote, _ = _git(["remote", "-v"], guard.session_repo)
    _, status, _ = _git(["status", "--short"], guard.session_repo)
    _, diff_stat, _ = _git(["diff", "--stat"], guard.session_repo)
    _, recent, _ = _git(
        ["log", f"-{params.max_commits}", "--pretty=format:%h%x09%ad%x09%s", "--date=short"],
        guard.session_repo,
    )
    data = {
        "branch": branch,
        "remote": remote.splitlines(),
        "status": status.splitlines(),
        "diff_stat": diff_stat,
        "recent_commits": recent.splitlines(),
    }
    lines = ["# Git 摘要", "", f"- 当前分支：`{branch or '<detached>'}`"]
    lines.extend(["", "## Remote", "```text", remote or "<none>", "```"])
    lines.extend(["", "## 工作区状态", "```text", status or "clean", "```"])
    lines.extend(["", "## Diff Stat", "```text", diff_stat or "<none>", "```"])
    lines.extend(["", "## 最近提交", "```text", recent or "<none>", "```"])
    return _format(data, "\n".join(lines), params.response_format)


def repo_save_report(params: SaveReportInput, config: AppConfig | None = None) -> str:
    """Save a Markdown report under the configured outputs directory."""

    cfg = config or load_config()
    guard = PathGuard(cfg, cfg.project_root, validate_session=False)
    safe_name = Path(params.filename).name
    if not safe_name.endswith(".md"):
        safe_name += ".md"
    output_path = guard.resolve_write_path(safe_name)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(params.content, encoding="utf-8")
    data = {"path": output_path.as_posix(), "chars": len(params.content)}
    markdown = f"报告已保存：`{output_path}`（{len(params.content)} 字符）"
    return _format(data, markdown, params.response_format)
