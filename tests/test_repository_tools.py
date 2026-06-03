import json
from pathlib import Path

from repopilot.config import AppConfig, LimitSettings, PermissionSettings
from repopilot.tools.repository import (
    DetectStackInput,
    GitSummaryInput,
    ListTreeInput,
    ReadFileInput,
    SaveReportInput,
    SearchTextInput,
    repo_detect_stack,
    repo_git_summary,
    repo_list_tree,
    repo_read_file,
    repo_save_report,
    repo_search_text,
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
