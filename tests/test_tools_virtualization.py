from unittest.mock import MagicMock, patch

import pytest

from bazzite_mcp.runner import ToolError
from bazzite_mcp.tools.virtualization import manage_vm


@patch("bazzite_mcp.tools.virtualization.run_audited")
def test_manage_vm_setup(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
    result = manage_vm("setup")
    assert "completed" in result.lower()
    assert "setup-virtualization virt-on" in mock_run.call_args[0][0]


@patch("bazzite_mcp.tools.virtualization.run_command")
def test_manage_vm_list(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="vm-a", stderr="")
    result = manage_vm("list")
    assert result == "vm-a"


@patch("bazzite_mcp.tools.virtualization.run_command")
def test_manage_vm_status(mock_run: MagicMock) -> None:
    mock_run.side_effect = [
        MagicMock(returncode=0, stdout="Virtualization: VT-x", stderr=""),
        MagicMock(returncode=0, stdout="active", stderr=""),
        MagicMock(returncode=0, stdout="enabled", stderr=""),
        MagicMock(returncode=0, stdout="Name: default\nActive: yes", stderr=""),
    ]
    result = manage_vm("status")
    assert "libvirtd" in result
    assert "default" in result


@patch("bazzite_mcp.tools.virtualization.run_audited")
def test_manage_vm_setup_raises_on_error(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="failed")
    with pytest.raises(ToolError, match="Failed to run virtualization setup"):
        manage_vm("setup")
