from unittest.mock import MagicMock, patch

from bazzite_mcp.tools.system import (
    disk_usage,
    process_list,
    system_info,
)


@patch("bazzite_mcp.tools.system.run_command")
def test_system_info(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="Bazzite 43", stderr="")
    result = system_info()
    assert "Bazzite" in result


@patch("bazzite_mcp.tools.system.run_command")
def test_disk_usage(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="/dev/sda1 50G 20G 30G 40% /",
        stderr="",
    )
    result = disk_usage()
    assert "/" in result


@patch("bazzite_mcp.tools.system.run_command")
def test_process_list(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="PID USER %CPU\n1 root 0.0", stderr="")
    result = process_list()
    assert "PID" in result
