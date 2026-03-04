from unittest.mock import MagicMock, patch

import pytest

from bazzite_mcp.runner import ToolError
from bazzite_mcp.tools.ujust import ujust_list, ujust_run, ujust_show


@patch("bazzite_mcp.tools.ujust.run_command")
def test_ujust_list(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="update\nsetup-waydroid\nenable-tailscale",
        stderr="",
    )
    result = ujust_list()
    assert "update" in result
    mock_run.assert_called_once()


@patch("bazzite_mcp.tools.ujust.run_command")
def test_ujust_list_with_filter(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="update\nsetup-waydroid\nenable-tailscale",
        stderr="",
    )
    result = ujust_list(filter="setup")
    assert "setup-waydroid" in result


@patch("bazzite_mcp.tools.ujust.run_command")
def test_ujust_show(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(
        returncode=0, stdout="#!/bin/bash\necho hello", stderr=""
    )
    result = ujust_show("update")
    assert "echo hello" in result


@patch("bazzite_mcp.tools.ujust.run_command")
def test_ujust_list_falls_back_to_full_list(mock_run: MagicMock) -> None:
    mock_run.side_effect = [
        MagicMock(returncode=1, stdout="", stderr="unknown option --summary"),
        MagicMock(returncode=0, stdout="update\nsetup-waydroid", stderr=""),
    ]

    result = ujust_list()

    assert "update" in result
    assert mock_run.call_count == 2
    assert mock_run.call_args_list[0].args[0] == "ujust --summary"
    assert mock_run.call_args_list[1].args[0] == "ujust"


@patch("bazzite_mcp.tools.ujust.run_command")
def test_ujust_run_help_uses_usage(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="usage output", stderr="")

    result = ujust_run("setup-virtualization help")

    assert result == "usage output"
    mock_run.assert_called_once_with("ujust --usage setup-virtualization")


@patch("bazzite_mcp.tools.ujust.run_command")
def test_ujust_run_blocks_interactive_recipe_without_option(
    mock_run: MagicMock,
) -> None:
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout='my_recipe:\n    OPTION=$(Choose "one" "two")',
        stderr="",
    )

    with pytest.raises(ToolError):
        ujust_run("my_recipe")


@patch("bazzite_mcp.tools.ujust.run_audited")
@patch("bazzite_mcp.tools.ujust.run_command")
def test_ujust_run_executes_non_interactive_recipe(
    mock_run_command: MagicMock,
    mock_run_audited: MagicMock,
) -> None:
    mock_run_command.return_value = MagicMock(returncode=0, stdout="recipe", stderr="")
    mock_run_audited.return_value = MagicMock(returncode=0, stdout="ok", stderr="")

    result = ujust_run("update")

    assert result == "ok"
    mock_run_audited.assert_called_once()
