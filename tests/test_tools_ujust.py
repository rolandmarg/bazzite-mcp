from unittest.mock import MagicMock, patch

from bazzite_mcp.tools.ujust import ujust_list, ujust_show


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
    mock_run.return_value = MagicMock(returncode=0, stdout="#!/bin/bash\necho hello", stderr="")
    result = ujust_show("update")
    assert "echo hello" in result
