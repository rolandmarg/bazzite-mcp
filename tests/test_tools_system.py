from unittest.mock import MagicMock, patch

from bazzite_mcp.runner import CommandResult
from bazzite_mcp.tools.system import (
    disk_usage,
    journal_logs,
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


# --- journal_logs tests ---


@patch("bazzite_mcp.tools.system.run_command")
def test_journal_logs_with_unit(mock_run: MagicMock) -> None:
    mock_run.return_value = CommandResult(
        returncode=0, stdout="Mar 03 10:00:00 host sshd[1234]: Accepted", stderr=""
    )
    result = journal_logs(unit="sshd")
    assert "sshd" in result or "Accepted" in result
    cmd = mock_run.call_args[0][0]
    assert "-u sshd" in cmd


@patch("bazzite_mcp.tools.system.run_command")
def test_journal_logs_with_priority(mock_run: MagicMock) -> None:
    mock_run.return_value = CommandResult(
        returncode=0, stdout="Mar 03 err kernel: oops", stderr=""
    )
    result = journal_logs(priority="err")
    assert "oops" in result or "err" in result
    cmd = mock_run.call_args[0][0]
    assert "-p err" in cmd


@patch("bazzite_mcp.tools.system.run_command")
def test_journal_logs_with_since(mock_run: MagicMock) -> None:
    mock_run.return_value = CommandResult(
        returncode=0, stdout="Mar 03 10:00:00 host kernel: boot", stderr=""
    )
    result = journal_logs(since="today")
    cmd = mock_run.call_args[0][0]
    assert '--since "today"' in cmd


@patch("bazzite_mcp.tools.system.run_command")
def test_journal_logs_default_no_filters(mock_run: MagicMock) -> None:
    mock_run.return_value = CommandResult(
        returncode=0, stdout="Mar 03 10:00:00 host kernel: message", stderr=""
    )
    result = journal_logs()
    cmd = mock_run.call_args[0][0]
    assert cmd == "journalctl --no-pager -n 50"
    assert " -u " not in cmd
    assert " -p " not in cmd
    assert "--since" not in cmd


@patch("bazzite_mcp.tools.system.run_command")
def test_journal_logs_all_filters_combined(mock_run: MagicMock) -> None:
    mock_run.return_value = CommandResult(
        returncode=0, stdout="log output", stderr=""
    )
    result = journal_logs(unit="nginx", priority="warning", since="yesterday", lines=100)
    cmd = mock_run.call_args[0][0]
    assert "-n 100" in cmd
    assert "-u nginx" in cmd
    assert "-p warning" in cmd
    assert '--since "yesterday"' in cmd
