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


@patch("bazzite_mcp.tools.virtualization._host_resources")
@patch("bazzite_mcp.tools.virtualization.run_audited")
def test_manage_vm_create_default_uses_dynamic_defaults(
    mock_audited: MagicMock,
    mock_host_resources: MagicMock,
    tmp_path,
) -> None:
    mock_host_resources.return_value = (16384, 8)
    mock_audited.return_value = MagicMock(returncode=0, stdout="created", stderr="")

    iso = tmp_path / "windows.iso"
    iso.write_text("dummy", encoding="utf-8")

    result = manage_vm("create_default", name="lab-vm", iso_path=str(iso))
    assert "windows-untrusted-lite" in result

    command = mock_audited.call_args[0][0]
    assert "--memory 4096" in command
    assert "--vcpus 4" in command
    assert "size=64" in command


@patch("bazzite_mcp.tools.virtualization.run_audited")
def test_manage_vm_create_default_requires_iso_path(
    mock_audited: MagicMock,
) -> None:
    mock_audited.return_value = MagicMock(returncode=0, stdout="", stderr="")
    with pytest.raises(ToolError, match="iso_path"):
        manage_vm("create_default", name="lab-vm")


@patch("bazzite_mcp.tools.virtualization._host_resources")
@patch("bazzite_mcp.tools.virtualization.run_audited")
def test_manage_vm_create_default_honors_overrides(
    mock_audited: MagicMock,
    mock_host_resources: MagicMock,
    tmp_path,
) -> None:
    mock_host_resources.return_value = (32768, 16)
    mock_audited.return_value = MagicMock(returncode=0, stdout="created", stderr="")
    iso = tmp_path / "win11.iso"
    iso.write_text("dummy", encoding="utf-8")

    manage_vm(
        "create_default",
        name="custom-vm",
        iso_path=str(iso),
        ram_mb=6144,
        vcpus=3,
        disk_gb=80,
    )

    command = mock_audited.call_args[0][0]
    assert "--memory 6144" in command
    assert "--vcpus 3" in command
    assert "size=80" in command


@patch("bazzite_mcp.tools.virtualization.run_audited")
def test_manage_vm_start(mock_audited: MagicMock) -> None:
    mock_audited.return_value = MagicMock(returncode=0, stdout="started", stderr="")
    result = manage_vm("start", name="lab-vm")
    assert "started" in result


@patch("bazzite_mcp.tools.virtualization.run_audited")
def test_manage_vm_snapshot_create(mock_audited: MagicMock) -> None:
    mock_audited.return_value = MagicMock(returncode=0, stdout="snap", stderr="")
    result = manage_vm("snapshot_create", name="lab-vm", snapshot="baseline")
    assert "snap" in result
    assert "snapshot-create-as" in mock_audited.call_args[0][0]


@patch("bazzite_mcp.tools.virtualization.run_command")
def test_manage_vm_delete_blocks_running(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="running", stderr="")
    with pytest.raises(ToolError, match="running"):
        manage_vm("delete", name="lab-vm")


@patch("bazzite_mcp.tools.virtualization.run_command")
@patch("bazzite_mcp.tools.virtualization.run_audited")
def test_manage_vm_delete_with_storage(
    mock_audited: MagicMock,
    mock_run: MagicMock,
) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="shut off", stderr="")
    mock_audited.return_value = MagicMock(returncode=0, stdout="deleted", stderr="")

    result = manage_vm("delete", name="lab-vm", delete_storage=True)
    assert "deleted" in result
    assert "--remove-all-storage" in mock_audited.call_args[0][0]
