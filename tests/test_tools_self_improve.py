from pathlib import Path
from unittest.mock import MagicMock, patch

from bazzite_mcp.tools.self_improve import (
    contribute_fix,
    get_server_source,
    list_improvements,
    suggest_improvement,
)


@patch("bazzite_mcp.tools.self_improve.run_command")
def test_suggest_improvement_creates_issue(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="https://github.com/rolandmarg/bazzite-mcp/issues/1",
        stderr="",
    )
    result = suggest_improvement(
        title="Add Bluetooth toggle tool",
        description=(
            "There is no tool to toggle Bluetooth on/off. "
            "Should add a manage_bluetooth tool."
        ),
        category="missing-tool",
    )
    assert "issue" in result.lower() or "github" in result.lower()


@patch("bazzite_mcp.tools.self_improve.run_command")
def test_list_improvements(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="#1 Add Bluetooth toggle\n#2 Fix audio switching",
        stderr="",
    )
    result = list_improvements()
    assert "#1" in result


# --- get_server_source tests ---


@patch("bazzite_mcp.tools.self_improve._repo_local")
def test_get_server_source_path_traversal_blocked(mock_repo: MagicMock, tmp_path: Path) -> None:
    mock_repo.return_value = str(tmp_path)
    result = get_server_source("../../etc/passwd")
    assert "must be inside" in result.lower()


@patch("bazzite_mcp.tools.self_improve._repo_local")
def test_get_server_source_reads_valid_file(mock_repo: MagicMock, tmp_path: Path) -> None:
    mock_repo.return_value = str(tmp_path)
    test_file = tmp_path / "src" / "example.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("print('hello')", encoding="utf-8")
    result = get_server_source("src/example.py")
    assert result == "print('hello')"


@patch("bazzite_mcp.tools.self_improve._repo_local")
def test_get_server_source_file_not_found(mock_repo: MagicMock, tmp_path: Path) -> None:
    mock_repo.return_value = str(tmp_path)
    result = get_server_source("nonexistent.py")
    assert "not found" in result.lower()


# --- contribute_fix tests ---


@patch("bazzite_mcp.tools.self_improve._repo_slug", return_value="rolandmarg/bazzite-mcp")
@patch("bazzite_mcp.tools.self_improve._repo_local", return_value="/tmp/repo")
@patch("bazzite_mcp.tools.self_improve.run_command")
@patch("bazzite_mcp.tools.self_improve.run_audited")
def test_contribute_fix_successful_pr(
    mock_audited: MagicMock, mock_run: MagicMock, mock_local: MagicMock, mock_slug: MagicMock
) -> None:
    # run_audited handles branch creation
    mock_audited.return_value = MagicMock(returncode=0, stdout="", stderr="")
    # run_command handles commit, push, pr create, checkout main
    mock_run.side_effect = [
        MagicMock(returncode=0, stdout="", stderr=""),       # commit
        MagicMock(returncode=0, stdout="", stderr=""),       # push
        MagicMock(returncode=0, stdout="https://github.com/rolandmarg/bazzite-mcp/pull/42", stderr=""),  # pr create
        MagicMock(returncode=0, stdout="", stderr=""),       # checkout main
    ]
    result = contribute_fix("fix/audio", "Fix audio switching bug", "src/tools/audio.py")
    assert "PR created" in result
    assert "https://github.com" in result


@patch("bazzite_mcp.tools.self_improve._repo_slug", return_value="rolandmarg/bazzite-mcp")
@patch("bazzite_mcp.tools.self_improve._repo_local", return_value="/tmp/repo")
@patch("bazzite_mcp.tools.self_improve.run_command")
@patch("bazzite_mcp.tools.self_improve.run_audited")
def test_contribute_fix_branch_creation_failure(
    mock_audited: MagicMock, mock_run: MagicMock, mock_local: MagicMock, mock_slug: MagicMock
) -> None:
    mock_audited.return_value = MagicMock(returncode=1, stdout="", stderr="branch already exists")
    result = contribute_fix("fix/audio", "Fix audio switching bug", "src/tools/audio.py")
    assert "Failed to create branch" in result
    assert "already exists" in result
