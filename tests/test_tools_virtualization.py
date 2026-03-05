from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bazzite_mcp.runner import ToolError
from bazzite_mcp.tools.virtualization import manage_vm


def _ok(stdout: str = "") -> MagicMock:
    return MagicMock(returncode=0, stdout=stdout, stderr="")


def _preflight_ok_command(command: str) -> MagicMock:
    if command == "lscpu":
        return _ok("Virtualization: VT-x")
    if command == "virt-install --version":
        return _ok("4.1")
    if command == "virsh --version":
        return _ok("10.0")
    if command == "systemctl is-enabled libvirtd":
        return _ok("enabled")
    if command == "systemctl is-active libvirtd":
        return _ok("active")
    if command == "virsh net-info default":
        return _ok("Name: default\nActive: yes")
    if command == "lspci":
        return _ok("00:02.0 VGA compatible controller: Mock GPU")
    if command == "rpm-ostree status":
        return _ok("State: idle\nDeployments:\n● ostree-image-signed:docker://mock")
    if command.startswith("virsh domstate"):
        return _ok("shut off")
    return _ok("")


@patch("bazzite_mcp.tools.virtualization.run_command")
@patch("bazzite_mcp.tools.virtualization.run_audited")
def test_manage_vm_prepare_atomic(
    mock_audited: MagicMock,
    mock_command: MagicMock,
    tmp_path: Path,
) -> None:
    mock_audited.return_value = _ok("ok")
    mock_command.side_effect = _preflight_ok_command

    with patch(
        "bazzite_mcp.tools.virtualization.VM_OPERATION_STATE_FILE",
        tmp_path / "vm-operation.json",
    ):
        result = manage_vm("prepare")

    assert "atomic" in result.lower()
    assert "state: applied" in result
    assert "setup-virtualization virt-on" in mock_audited.call_args[0][0]


@patch("bazzite_mcp.tools.virtualization.run_command")
@patch("bazzite_mcp.tools.virtualization.run_audited")
def test_manage_vm_prepare_reboot_required(
    mock_audited: MagicMock,
    mock_command: MagicMock,
    tmp_path: Path,
) -> None:
    mock_audited.return_value = _ok("ok")

    def _side_effect(command: str) -> MagicMock:
        if command == "rpm-ostree status":
            return _ok(
                "State: idle\nDeployments:\nostree-image-signed:docker://pending\n"
                "● ostree-image-signed:docker://current"
            )
        return _preflight_ok_command(command)

    mock_command.side_effect = _side_effect

    with patch(
        "bazzite_mcp.tools.virtualization.VM_OPERATION_STATE_FILE",
        tmp_path / "vm-operation.json",
    ):
        result = manage_vm("prepare")
        state = json.loads((tmp_path / "vm-operation.json").read_text(encoding="utf-8"))

    assert "state: reboot_required" in result
    assert state["state"] == "reboot_required"


@patch("bazzite_mcp.tools.virtualization._vm_prepare")
def test_manage_vm_setup_alias(mock_prepare: MagicMock) -> None:
    mock_prepare.return_value = "prepared"
    assert manage_vm("setup") == "prepared"


@patch("bazzite_mcp.tools.virtualization.run_command")
def test_manage_vm_preflight_reports_missing_dependency(mock_run: MagicMock) -> None:
    def _side_effect(command: str) -> MagicMock:
        result = _preflight_ok_command(command)
        if command == "virt-install --version":
            result.returncode = 1
            result.stdout = ""
            result.stderr = "not found"
        return result

    mock_run.side_effect = _side_effect

    result = manage_vm("preflight")
    assert "ready: no" in result
    assert "missing_dependency" in result


@patch("bazzite_mcp.tools.virtualization.run_command")
def test_manage_vm_status(mock_run: MagicMock) -> None:
    mock_run.side_effect = [
        _ok("Virtualization: VT-x"),
        _ok("active"),
        _ok("enabled"),
        _ok("Name: default\nActive: yes"),
    ]
    result = manage_vm("status")
    assert "libvirtd" in result
    assert "default" in result
    assert "operation" in result


@patch("bazzite_mcp.tools.virtualization.run_audited")
def test_manage_vm_prepare_raises_on_error(mock_run: MagicMock, tmp_path: Path) -> None:
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="failed")

    with patch(
        "bazzite_mcp.tools.virtualization.VM_OPERATION_STATE_FILE",
        tmp_path / "vm-operation.json",
    ):
        with pytest.raises(ToolError, match="Atomic operation"):
            manage_vm("prepare")


@patch("bazzite_mcp.tools.virtualization._host_resources")
@patch("bazzite_mcp.tools.virtualization.run_command")
@patch("bazzite_mcp.tools.virtualization.run_audited")
def test_manage_vm_create_default_uses_dynamic_defaults(
    mock_audited: MagicMock,
    mock_command: MagicMock,
    mock_host_resources: MagicMock,
    tmp_path: Path,
) -> None:
    mock_host_resources.return_value = (16384, 8)
    mock_audited.return_value = _ok("created")
    mock_command.side_effect = _preflight_ok_command

    iso = tmp_path / "windows.iso"
    iso.write_text("dummy", encoding="utf-8")

    with patch("bazzite_mcp.tools.virtualization.VM_STORAGE_DIR", tmp_path / "vms"):
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
    mock_audited.return_value = _ok("")
    with pytest.raises(ToolError, match="iso_path"):
        manage_vm("create_default", name="lab-vm")


@patch("bazzite_mcp.tools.virtualization._host_resources")
@patch("bazzite_mcp.tools.virtualization.run_command")
@patch("bazzite_mcp.tools.virtualization.run_audited")
def test_manage_vm_create_default_honors_overrides(
    mock_audited: MagicMock,
    mock_command: MagicMock,
    mock_host_resources: MagicMock,
    tmp_path: Path,
) -> None:
    mock_host_resources.return_value = (32768, 16)
    mock_audited.return_value = _ok("created")
    mock_command.side_effect = _preflight_ok_command
    iso = tmp_path / "win11.iso"
    iso.write_text("dummy", encoding="utf-8")

    with patch("bazzite_mcp.tools.virtualization.VM_STORAGE_DIR", tmp_path / "vms"):
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
    mock_audited.return_value = _ok("started")
    result = manage_vm("start", name="lab-vm")
    assert "started" in result


@patch("bazzite_mcp.tools.virtualization.run_audited")
def test_manage_vm_snapshot_create(mock_audited: MagicMock) -> None:
    mock_audited.return_value = _ok("snap")
    result = manage_vm("snapshot_create", name="lab-vm", snapshot="baseline")
    assert "snap" in result
    assert "snapshot-create-as" in mock_audited.call_args[0][0]


@patch("bazzite_mcp.tools.virtualization.run_command")
def test_manage_vm_delete_blocks_running(mock_run: MagicMock) -> None:
    mock_run.return_value = _ok("running")
    with pytest.raises(ToolError, match="running"):
        manage_vm("delete", name="lab-vm")


@patch("bazzite_mcp.tools.virtualization.run_command")
@patch("bazzite_mcp.tools.virtualization.run_audited")
def test_manage_vm_delete_with_storage(
    mock_audited: MagicMock,
    mock_run: MagicMock,
) -> None:
    mock_run.return_value = _ok("shut off")
    mock_audited.return_value = _ok("deleted")

    result = manage_vm("delete", name="lab-vm", delete_storage=True)
    assert "deleted" in result
    assert "--remove-all-storage" in mock_audited.call_args[0][0]


@patch("bazzite_mcp.tools.virtualization.run_audited")
def test_manage_vm_rollback(mock_audited: MagicMock, tmp_path: Path) -> None:
    mock_audited.return_value = _ok("rolled back")
    state_file = tmp_path / "vm-operation.json"
    state_file.write_text(
        json.dumps(
            {
                "operation": "prepare",
                "state": "applied",
                "rollback_steps": [
                    {
                        "label": "disable_virtualization",
                        "command": "ujust setup-virtualization virt-off",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with patch("bazzite_mcp.tools.virtualization.VM_OPERATION_STATE_FILE", state_file):
        result = manage_vm("rollback")

    assert "Rollback completed" in result
