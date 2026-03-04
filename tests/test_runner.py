import pytest
import subprocess
from unittest.mock import MagicMock, patch

from bazzite_mcp.guardrails import GuardrailError
from bazzite_mcp.runner import run_command, run_audited


def test_run_simple_command() -> None:
    result = run_command("echo hello")
    assert result.returncode == 0
    assert "hello" in result.stdout


def test_run_blocked_command() -> None:
    with pytest.raises(GuardrailError):
        run_command("rm -rf /")


def test_run_failing_command() -> None:
    result = run_command("false")
    assert result.returncode != 0


def test_warning_surfaced_in_stdout() -> None:
    result = run_command("rpm-ostree install htop")
    assert result.warning is not None
    assert "WARNING:" in result.stdout
    assert "LAST RESORT" in result.stdout


def test_run_audited_logs_action(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    result = run_audited(
        "echo installed",
        tool="install_package",
        args={"package": "test", "method": "brew"},
        rollback="brew uninstall test",
    )
    assert result.returncode == 0
    assert "installed" in result.stdout

    from bazzite_mcp.audit import AuditLog

    log = AuditLog()
    entries = log.query(tool="install_package")
    assert len(entries) == 1
    assert entries[0]["rollback"] == "brew uninstall test"
    assert entries[0]["result"] == "success"


@patch("bazzite_mcp.runner.subprocess.run")
def test_run_command_non_interactive_execution(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")

    run_command("echo hello")

    _, kwargs = mock_run.call_args
    assert kwargs["stdin"] == subprocess.DEVNULL
    assert kwargs["start_new_session"] is True
