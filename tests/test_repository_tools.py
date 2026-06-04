import json
import subprocess
from pathlib import Path

from repopilot.config import AppConfig, LimitSettings, PermissionSettings
from repopilot.tools.repository import (
    DetectStackInput,
    GitSummaryInput,
    ListTreeInput,
    ReadFileInput,
    SaveReportInput,
    SearchTextInput,
    SymbolMapInput,
    repo_detect_stack,
    repo_git_summary,
    repo_list_tree,
    repo_read_file,
    repo_save_report,
    repo_search_text,
    repo_symbol_map,
)


def make_config(root: Path, out: Path) -> AppConfig:
    return AppConfig(
        permissions=PermissionSettings(
            readable_roots=[str(root)],
            writable_roots=[str(out)],
            deny_patterns=[
                "**/.env",
                "**/.git/**",
                "**/.pytest_cache",
                "**/.pytest_cache/**",
                "**/__pycache__/**",
                "**/*.egg-info",
                "**/*.egg-info/**",
            ],
        ),
        limits=LimitSettings(max_file_chars=8, max_search_results=2, max_tree_entries=20),
        project_root=root,
    )


def test_read_file_truncates_text(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("hello world", encoding="utf-8")
    config = make_config(tmp_path, tmp_path / "outputs")

    text = repo_read_file(ReadFileInput(repo_path=str(repo), path="README.md"), config)

    assert "hello wo" in text
    assert "已截断" in text

    payload = repo_read_file(
        ReadFileInput(repo_path=str(repo), path="README.md", response_format="json"),
        config,
    )
    data = json.loads(payload)
    assert data["returned_chars"] == 8
    assert data["truncated"] is True


def test_tree_and_stack_detection(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'", encoding="utf-8")
    (repo / "src").mkdir()
    config = make_config(tmp_path, tmp_path / "outputs")

    tree = repo_list_tree(ListTreeInput(repo_path=str(repo), max_depth=2), config)
    stack = repo_detect_stack(DetectStackInput(repo_path=str(repo)), config)

    assert "pyproject.toml" in tree
    assert "Python" in stack


def test_stack_detection_reads_pyproject_clues(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        """
[project]
name = "sample"

[project.scripts]
sample = "sample.cli:app"

[project.optional-dependencies]
dev = ["pytest"]

[tool.pytest.ini_options]
testpaths = ["tests"]
""",
        encoding="utf-8",
    )
    config = make_config(tmp_path, tmp_path / "outputs")

    stack = repo_detect_stack(DetectStackInput(repo_path=str(repo)), config)

    assert "script `sample`" in stack
    assert "`pytest`" in stack
    assert "`dev`" in stack


def test_tree_hides_generated_metadata(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".pytest_cache").mkdir()
    (repo / ".pytest_cache" / "README.md").write_text("cache", encoding="utf-8")
    (repo / "src").mkdir()
    (repo / "src" / "sample.egg-info").mkdir()
    (repo / "src" / "sample.egg-info" / "PKG-INFO").write_text("metadata", encoding="utf-8")
    (repo / "README.md").write_text("hello", encoding="utf-8")
    config = make_config(tmp_path, tmp_path / "outputs")

    tree = repo_list_tree(ListTreeInput(repo_path=str(repo), max_depth=3), config)

    assert "README.md" in tree
    assert ".pytest_cache" not in tree
    assert "sample.egg-info" not in tree


def test_tree_and_stack_skip_common_generated_directories(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.20)", encoding="utf-8")
    build = repo / "build"
    build.mkdir()
    (build / "generated.csproj").write_text("<Project />", encoding="utf-8")
    (build / "CMakeCache.txt").write_text("cache", encoding="utf-8")
    config = make_config(tmp_path, tmp_path / "outputs")

    tree = repo_list_tree(ListTreeInput(repo_path=str(repo), max_depth=3), config)
    stack = repo_detect_stack(DetectStackInput(repo_path=str(repo)), config)

    assert "CMakeLists.txt" in tree
    assert "build" not in tree
    assert "C/C++" in stack
    assert ".NET" not in stack


def test_gitignore_controls_tree_read_search_and_stack(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, stdin=subprocess.DEVNULL, check=True, capture_output=True)
    (repo / ".gitignore").write_text("build/\n", encoding="utf-8")
    (repo / "README.md").write_text("visible needle", encoding="utf-8")
    build = repo / "build"
    build.mkdir()
    (build / "package.json").write_text('{"scripts":{"dev":"vite"},"needle":"hidden"}', encoding="utf-8")
    config = make_config(tmp_path, tmp_path / "outputs")

    tree = repo_list_tree(ListTreeInput(repo_path=str(repo), max_depth=3), config)
    read = repo_read_file(ReadFileInput(repo_path=str(repo), path="build/package.json"), config)
    search = repo_search_text(SearchTextInput(repo_path=str(repo), query="needle"), config)
    stack = repo_detect_stack(DetectStackInput(repo_path=str(repo)), config)

    assert "README.md" in tree
    assert "build" not in tree
    assert "Git ignore" in read
    assert "README.md" in search
    assert "build/package.json" not in search
    assert "Node.js" not in stack


def test_git_repo_does_not_apply_fallback_ignore_when_git_allows_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, stdin=subprocess.DEVNULL, check=True, capture_output=True)
    (repo / ".gitignore").write_text("# build artifacts are intentionally visible in this fixture\n", encoding="utf-8")
    build = repo / "build"
    build.mkdir()
    (build / "keep.txt").write_text("visible", encoding="utf-8")
    config = make_config(tmp_path, tmp_path / "outputs")

    tree = repo_list_tree(ListTreeInput(repo_path=str(repo), max_depth=2), config)

    assert "build/" in tree
    assert "build/keep.txt" in tree


def test_tree_and_search_skip_writable_outputs(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    out = repo / "outputs"
    out.mkdir()
    (out / "RepoPilot-overview.md").write_text("needle", encoding="utf-8")
    (repo / "README.md").write_text("needle", encoding="utf-8")
    config = make_config(tmp_path, out)

    tree = repo_list_tree(ListTreeInput(repo_path=str(repo), max_depth=2), config)
    search = repo_search_text(SearchTextInput(repo_path=str(repo), query="needle"), config)

    assert "outputs" not in tree
    assert "RepoPilot-overview.md" not in tree
    assert "README.md" in search
    assert "RepoPilot-overview.md" not in search


def test_git_summary_non_git_repo_is_informational(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config = make_config(tmp_path, tmp_path / "outputs")

    summary = repo_git_summary(GitSummaryInput(repo_path=str(repo)), config)

    assert "已跳过 Git 摘要" in summary
    assert not summary.startswith("Error:")


def test_symbol_map_extracts_python_ts_and_cpp_symbols(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text(
        """
class Service:
    def run(self, value):
        return value

async def load_config(path):
    return path
""",
        encoding="utf-8",
    )
    (repo / "ui.ts").write_text(
        """
export class Panel {}
export function renderPanel(target: string) {}
const useThing = (value: string) => value
""",
        encoding="utf-8",
    )
    (repo / "core.cpp").write_text(
        """
struct Point {};
int add(int left, int right) {
  return left + right;
}
""",
        encoding="utf-8",
    )
    config = make_config(tmp_path, tmp_path / "outputs")

    text = repo_symbol_map(SymbolMapInput(repo_path=str(repo)), config)
    payload = repo_symbol_map(SymbolMapInput(repo_path=str(repo), response_format="json"), config)
    data = json.loads(payload)

    assert "Service" in text
    assert "renderPanel" in text
    assert "Point" in text
    assert any(file["path"] == "app.py" for file in data["files"])



def test_search_text_limits_results(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.txt").write_text("alpha\nalpha\nalpha\n", encoding="utf-8")
    config = make_config(tmp_path, tmp_path / "outputs")

    text = repo_search_text(SearchTextInput(repo_path=str(repo), query="alpha"), config)

    assert text.count("a.txt") <= 2


def test_save_report_writes_only_outputs(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    out.mkdir()
    config = make_config(tmp_path, out)

    result = repo_save_report(SaveReportInput(filename="report.md", content="# ok"), config)

    assert (out / "report.md").exists()
    assert "报告已保存" in result


def test_save_report_does_not_require_project_root_read_access(tmp_path: Path) -> None:
    readable = tmp_path / "repos"
    project = tmp_path / "app"
    out = project / "outputs"
    readable.mkdir()
    out.mkdir(parents=True)
    config = AppConfig(
        permissions=PermissionSettings(
            readable_roots=[str(readable)],
            writable_roots=[str(out)],
            deny_patterns=["**/.env"],
        ),
        project_root=project,
    )

    repo_save_report(SaveReportInput(filename="../report.md", content="# ok"), config)

    assert (out / "report.md").exists()
