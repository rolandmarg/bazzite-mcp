import pytest

from bazzite_mcp.guardrails import GuardrailError
from bazzite_mcp.runner import run_command


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
