from unittest.mock import MagicMock, call, patch

from bazzite_mcp.runner import CommandResult
from bazzite_mcp.tools.services import manage_firewall, manage_service, network_status, service_status


@patch("bazzite_mcp.tools.services.run_command")
def test_service_status(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="active (running)", stderr="")
    result = service_status("NetworkManager")
    assert "active" in result


@patch("bazzite_mcp.tools.services.run_command")
def test_network_status(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="eth0: connected", stderr="")
    result = network_status()
    assert "connected" in result


# --- manage_service tests ---


@patch("bazzite_mcp.tools.services.run_audited")
def test_manage_service_start(mock_audited: MagicMock) -> None:
    mock_audited.return_value = CommandResult(returncode=0, stdout="", stderr="")
    result = manage_service("bluetooth.service", "start")
    assert "successful" in result.lower()
    # Verify the rollback for start is stop
    _, kwargs = mock_audited.call_args
    assert "stop" in kwargs.get("rollback", "")


@patch("bazzite_mcp.tools.services.run_audited")
def test_manage_service_stop(mock_audited: MagicMock) -> None:
    mock_audited.return_value = CommandResult(returncode=0, stdout="", stderr="")
    result = manage_service("bluetooth.service", "stop")
    assert "successful" in result.lower()
    _, kwargs = mock_audited.call_args
    assert "start" in kwargs.get("rollback", "")


@patch("bazzite_mcp.tools.services.run_audited")
def test_manage_service_enable(mock_audited: MagicMock) -> None:
    mock_audited.return_value = CommandResult(returncode=0, stdout="", stderr="")
    result = manage_service("bluetooth.service", "enable")
    assert "successful" in result.lower()
    _, kwargs = mock_audited.call_args
    assert "disable" in kwargs.get("rollback", "")


@patch("bazzite_mcp.tools.services.run_audited")
def test_manage_service_disable(mock_audited: MagicMock) -> None:
    mock_audited.return_value = CommandResult(returncode=0, stdout="", stderr="")
    result = manage_service("bluetooth.service", "disable")
    assert "successful" in result.lower()
    _, kwargs = mock_audited.call_args
    assert "enable" in kwargs.get("rollback", "")


def test_manage_service_invalid_action() -> None:
    result = manage_service("bluetooth.service", "destroy")
    assert "Unknown action" in result
    assert "destroy" in result


@patch("bazzite_mcp.tools.services.run_audited")
def test_manage_service_rollback_command_construction(mock_audited: MagicMock) -> None:
    """Verify the complete rollback command is correctly constructed."""
    mock_audited.return_value = CommandResult(returncode=0, stdout="", stderr="")
    manage_service("sshd", "enable --now", user=True)
    _, kwargs = mock_audited.call_args
    assert kwargs["rollback"] == "systemctl --user disable --now sshd"


# --- manage_firewall tests ---


@patch("bazzite_mcp.tools.services.run_audited")
def test_manage_firewall_add_port(mock_audited: MagicMock) -> None:
    mock_audited.return_value = CommandResult(returncode=0, stdout="success", stderr="")
    result = manage_firewall("add-port", port="8080/tcp")
    assert "success" in result
    # Verify the command includes the port
    args, kwargs = mock_audited.call_args
    assert "add-port=8080/tcp" in args[0]
    # Verify rollback is remove-port
    assert "remove-port=8080/tcp" in kwargs["rollback"]


@patch("bazzite_mcp.tools.services.run_audited")
def test_manage_firewall_remove_port(mock_audited: MagicMock) -> None:
    mock_audited.return_value = CommandResult(returncode=0, stdout="success", stderr="")
    result = manage_firewall("remove-port", port="8080/tcp")
    assert "success" in result
    args, kwargs = mock_audited.call_args
    assert "remove-port=8080/tcp" in args[0]
    # Rollback for remove-port is add-port
    assert "add-port=8080/tcp" in kwargs["rollback"]


@patch("bazzite_mcp.tools.services.run_audited")
def test_manage_firewall_rollback_inverse_mapping(mock_audited: MagicMock) -> None:
    """Verify add-service rollback is remove-service and vice versa."""
    mock_audited.return_value = CommandResult(returncode=0, stdout="success", stderr="")

    manage_firewall("add-service", service="http")
    _, kwargs = mock_audited.call_args
    assert "remove-service=http" in kwargs["rollback"]

    manage_firewall("remove-service", service="http")
    _, kwargs = mock_audited.call_args
    assert "add-service=http" in kwargs["rollback"]
