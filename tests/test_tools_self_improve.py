from unittest.mock import MagicMock, patch

from bazzite_mcp.tools.self_improve import list_improvements, suggest_improvement


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
