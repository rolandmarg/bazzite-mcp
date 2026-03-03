from unittest.mock import MagicMock, patch

from bazzite_mcp.tools.services import network_status, service_status


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
