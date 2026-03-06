from unittest.mock import MagicMock, call, patch

import pytest

from bazzite_mcp.runner import CommandResult, ToolError
from bazzite_mcp.tools.services import (
    manage_firewall,
    manage_network,
    manage_service,
)
from bazzite_mcp.tools.services.network import _network_status
from bazzite_mcp.tools.services.systemd import _service_status


@patch("bazzite_mcp.tools.services.systemd.run_command")
def test_service_status(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(
        returncode=0, stdout="active (running)", stderr=""
    )
    result = _service_status("NetworkManager")
    assert "active" in result


@patch("bazzite_mcp.tools.services.network.run_command")
def test_network_status(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="eth0: connected", stderr="")
    result = _network_status()
    assert "connected" in result


# --- manage_service tests ---


@patch("bazzite_mcp.tools.services.systemd.run_audited")
def test_manage_service_start(mock_audited: MagicMock) -> None:
    mock_audited.return_value = CommandResult(returncode=0, stdout="", stderr="")
    result = manage_service("bluetooth.service", "start")
    assert "successful" in result.lower()
    # Verify the rollback for start is stop
    _, kwargs = mock_audited.call_args
    assert "stop" in kwargs.get("rollback", [])


@patch("bazzite_mcp.tools.services.systemd.run_audited")
def test_manage_service_stop(mock_audited: MagicMock) -> None:
    mock_audited.return_value = CommandResult(returncode=0, stdout="", stderr="")
    result = manage_service("bluetooth.service", "stop")
    assert "successful" in result.lower()
    _, kwargs = mock_audited.call_args
    assert "start" in kwargs.get("rollback", [])


@patch("bazzite_mcp.tools.services.systemd.run_audited")
def test_manage_service_enable(mock_audited: MagicMock) -> None:
    mock_audited.return_value = CommandResult(returncode=0, stdout="", stderr="")
    result = manage_service("bluetooth.service", "enable")
    assert "successful" in result.lower()
    _, kwargs = mock_audited.call_args
    assert "disable" in kwargs.get("rollback", [])


@patch("bazzite_mcp.tools.services.systemd.run_audited")
def test_manage_service_disable(mock_audited: MagicMock) -> None:
    mock_audited.return_value = CommandResult(returncode=0, stdout="", stderr="")
    result = manage_service("bluetooth.service", "disable")
    assert "successful" in result.lower()
    _, kwargs = mock_audited.call_args
    assert "enable" in kwargs.get("rollback", [])


@patch("bazzite_mcp.tools.services.systemd.run_command")
def test_manage_service_status_action(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="active (running)", stderr="")
    result = manage_service("bluetooth.service", "status")
    assert "active" in result


@patch("bazzite_mcp.tools.services.systemd.run_command")
def test_manage_service_list_action(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="sshd.service enabled", stderr="")
    result = manage_service("ignored", "list", state="enabled")
    assert "sshd" in result


def test_manage_service_invalid_action() -> None:
    with pytest.raises(ToolError, match="destroy"):
        manage_service("bluetooth.service", "destroy")  # pyright: ignore[reportArgumentType]


@patch("bazzite_mcp.tools.services.systemd.run_audited")
def test_manage_service_rollback_command_construction(mock_audited: MagicMock) -> None:
    """Verify the complete rollback command is correctly constructed."""
    mock_audited.return_value = CommandResult(returncode=0, stdout="", stderr="")
    manage_service("sshd", "enable_now", user=True)
    _, kwargs = mock_audited.call_args
    assert kwargs["rollback"] == ["systemctl", "--user", "disable", "--now", "sshd"]


# --- manage_firewall tests ---


@patch("bazzite_mcp.tools.services.firewall.run_audited")
def test_manage_firewall_add_port(mock_audited: MagicMock) -> None:
    mock_audited.return_value = CommandResult(returncode=0, stdout="success", stderr="")
    result = manage_firewall("add_port", port="8080/tcp")
    assert "success" in result
    assert mock_audited.call_count == 2
    # Verify the command includes the port
    args, kwargs = mock_audited.call_args_list[0]
    assert "--add-port=8080/tcp" in args[0]
    # Verify rollback is remove-port
    assert "--remove-port=8080/tcp" in kwargs["rollback"]
    assert mock_audited.call_args_list[1].args[0] == ["pkexec", "firewall-cmd", "--reload"]


@patch("bazzite_mcp.tools.services.firewall.run_audited")
def test_manage_firewall_remove_port(mock_audited: MagicMock) -> None:
    mock_audited.return_value = CommandResult(returncode=0, stdout="success", stderr="")
    result = manage_firewall("remove_port", port="8080/tcp")
    assert "success" in result
    assert mock_audited.call_count == 2
    args, kwargs = mock_audited.call_args_list[0]
    assert "--remove-port=8080/tcp" in args[0]
    # Rollback for remove-port is add-port
    assert "--add-port=8080/tcp" in kwargs["rollback"]


@patch("bazzite_mcp.tools.services.firewall.run_audited")
def test_manage_firewall_rollback_inverse_mapping(mock_audited: MagicMock) -> None:
    """Verify add-service rollback is remove-service and vice versa."""
    mock_audited.return_value = CommandResult(returncode=0, stdout="success", stderr="")

    manage_firewall("add_service", service="http")
    _, kwargs = mock_audited.call_args_list[0]
    assert "--remove-service=http" in kwargs["rollback"]

    manage_firewall("remove_service", service="http")
    _, kwargs = mock_audited.call_args_list[2]
    assert "--add-service=http" in kwargs["rollback"]


# --- manage_network dispatcher tests ---


@patch("bazzite_mcp.tools.services.network.run_command")
def test_manage_network_status(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="eth0: connected", stderr="")
    result = manage_network("status")
    assert "connected" in result
