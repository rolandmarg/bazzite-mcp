from __future__ import annotations

import os
import re
import shlex
from datetime import datetime
from pathlib import Path
from typing import Literal

from bazzite_mcp.runner import ToolError, run_audited, run_command


VM_STORAGE_DIR = Path.home() / ".local" / "share" / "bazzite-mcp" / "vms"
DEFAULT_DISK_GB = 64


def _host_resources() -> tuple[int, int]:
    """Return host RAM (MB) and vCPU count."""
    total_ram_mb = 8192
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                total_kb = int(line.split()[1])
                total_ram_mb = total_kb // 1024
                break
    except (FileNotFoundError, OSError, ValueError, IndexError):
        pass

    vcpus = os.cpu_count() or 2
    return total_ram_mb, max(1, vcpus)


def _default_ram_mb(total_ram_mb: int) -> int:
    """Pick a conservative guest RAM default from host memory."""
    target = int(total_ram_mb * 0.25)
    floor = 2048 if total_ram_mb >= 4096 else 1024
    ceiling = max(floor, min(6144, total_ram_mb - 1024))
    return max(floor, min(ceiling, target))


def _default_vcpus(total_vcpus: int) -> int:
    """Pick a conservative guest vCPU default from host CPU count."""
    if total_vcpus <= 2:
        return total_vcpus
    return min(4, max(2, total_vcpus // 2))


def _validate_vm_name(name: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        raise ToolError(
            "Invalid VM name. Use only letters, digits, dot, underscore, and dash."
        )


def _resolve_iso_path(iso_path: str) -> Path:
    path = Path(iso_path).expanduser()
    if not path.is_file():
        raise ToolError(f"ISO path does not exist or is not a file: {path}")
    if path.suffix.lower() != ".iso":
        raise ToolError(f"Install media must be an .iso file: {path}")
    return path


def _create_default_vm(
    name: str,
    iso_path: str,
    ram_mb: int | None = None,
    vcpus: int | None = None,
    disk_gb: int | None = None,
) -> str:
    """Create a Windows-focused low-overhead VM profile for untrusted binaries."""
    _validate_vm_name(name)
    iso = _resolve_iso_path(iso_path)

    host_ram_mb, host_vcpus = _host_resources()
    effective_ram = ram_mb or _default_ram_mb(host_ram_mb)
    effective_vcpus = vcpus or _default_vcpus(host_vcpus)
    effective_disk = disk_gb or DEFAULT_DISK_GB

    if effective_ram < 1024:
        raise ToolError("ram_mb must be at least 1024")
    if effective_vcpus < 1:
        raise ToolError("vcpus must be at least 1")
    if effective_disk < 20:
        raise ToolError("disk_gb must be at least 20")

    VM_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    disk_path = VM_STORAGE_DIR / f"{name}.qcow2"
    if disk_path.exists():
        raise ToolError(
            f"Disk image already exists for '{name}': {disk_path}. "
            "Use a different name or delete the existing VM first."
        )

    sname = shlex.quote(name)
    siso = shlex.quote(str(iso))
    disk_spec = shlex.quote(
        f"path={disk_path},size={effective_disk},format=qcow2,bus=sata"
    )
    cmd = (
        f"virt-install --name {sname} --memory {effective_ram} --vcpus {effective_vcpus} "
        "--cpu host-passthrough --machine q35 --os-variant win10 "
        f"--disk {disk_spec} --cdrom {siso} "
        "--network network=default,model=e1000 "
        "--graphics spice --video qxl --channel spicevmc "
        "--noautoconsole --wait 0"
    )

    result = run_audited(
        cmd,
        tool="manage_vm",
        args={
            "action": "create_default",
            "name": name,
            "iso_path": str(iso),
            "ram_mb": effective_ram,
            "vcpus": effective_vcpus,
            "disk_gb": effective_disk,
            "profile": "windows-untrusted-lite",
        },
        rollback=f"virsh undefine {sname} --nvram --remove-all-storage",
    )
    if result.returncode != 0:
        raise ToolError(
            f"Failed to create VM '{name}': {result.stderr or result.stdout}"
        )

    return (
        f"Created VM '{name}' (windows-untrusted-lite).\n"
        f"RAM={effective_ram}MB, vCPUs={effective_vcpus}, disk={effective_disk}GB\n"
        f"ISO={iso}\n"
        "Recommended workflow: snapshot after clean install, then revert after each risky session."
    )


def _vm_control(name: str, action: Literal["start", "stop"]) -> str:
    """Start or stop a VM."""
    _validate_vm_name(name)
    sname = shlex.quote(name)
    cmd = "virsh start" if action == "start" else "virsh shutdown"
    result = run_audited(
        f"{cmd} {sname}",
        tool="manage_vm",
        args={"action": action, "name": name},
    )
    if result.returncode != 0:
        raise ToolError(
            f"Failed to {action} VM '{name}': {result.stderr or result.stdout}"
        )
    return result.stdout or f"VM '{name}' {action} command sent."


def _vm_delete(name: str, delete_storage: bool = False) -> str:
    """Undefine a VM and optionally remove attached storage."""
    _validate_vm_name(name)
    sname = shlex.quote(name)

    state_result = run_command(f"virsh domstate {sname}")
    if state_result.returncode == 0 and "running" in state_result.stdout.lower():
        raise ToolError(
            f"VM '{name}' is running. Stop it first with manage_vm(action='stop', name='{name}')."
        )

    cmd = f"virsh undefine {sname} --nvram"
    if delete_storage:
        cmd += " --remove-all-storage"

    result = run_audited(
        cmd,
        tool="manage_vm",
        args={"action": "delete", "name": name, "delete_storage": delete_storage},
    )
    if result.returncode != 0:
        raise ToolError(
            f"Failed to delete VM '{name}': {result.stderr or result.stdout}"
        )
    return result.stdout or f"Deleted VM '{name}'."


def _snapshot_list(name: str) -> str:
    """List snapshots for a VM."""
    _validate_vm_name(name)
    result = run_command(f"virsh snapshot-list {shlex.quote(name)}")
    if result.returncode != 0:
        raise ToolError(f"Failed to list snapshots for '{name}': {result.stderr}")
    return result.stdout


def _snapshot_create(name: str, snapshot: str | None = None) -> str:
    """Create a snapshot for a VM."""
    _validate_vm_name(name)
    snap_name = snapshot or datetime.now().strftime("snap-%Y%m%d-%H%M%S")
    cmd = (
        f"virsh snapshot-create-as {shlex.quote(name)} {shlex.quote(snap_name)} "
        f"--description {shlex.quote('bazzite-mcp snapshot')}"
    )
    result = run_audited(
        cmd,
        tool="manage_vm",
        args={"action": "snapshot_create", "name": name, "snapshot": snap_name},
    )
    if result.returncode != 0:
        raise ToolError(
            f"Failed to create snapshot '{snap_name}' for '{name}': {result.stderr or result.stdout}"
        )
    return result.stdout or f"Created snapshot '{snap_name}' for '{name}'."


def _snapshot_revert(name: str, snapshot: str) -> str:
    """Revert a VM to a snapshot."""
    _validate_vm_name(name)
    cmd = f"virsh snapshot-revert {shlex.quote(name)} {shlex.quote(snapshot)}"
    result = run_audited(
        cmd,
        tool="manage_vm",
        args={"action": "snapshot_revert", "name": name, "snapshot": snapshot},
    )
    if result.returncode != 0:
        raise ToolError(
            f"Failed to revert snapshot '{snapshot}' for '{name}': {result.stderr or result.stdout}"
        )
    return result.stdout or f"Reverted '{name}' to snapshot '{snapshot}'."


def _vm_status() -> str:
    """Report host virtualization readiness and libvirt state."""
    lines: list[str] = []

    cpu_result = run_command("lscpu")
    if cpu_result.returncode == 0:
        virt_lines = [
            line.strip()
            for line in cpu_result.stdout.splitlines()
            if "virtualization" in line.lower()
        ]
        if virt_lines:
            lines.append("CPU")
            lines.extend(f"  {line}" for line in virt_lines)

    active_result = run_command("systemctl is-active libvirtd")
    enabled_result = run_command("systemctl is-enabled libvirtd")
    lines.append("libvirtd")
    lines.append(f"  active:  {active_result.stdout.strip() or 'unknown'}")
    lines.append(f"  enabled: {enabled_result.stdout.strip() or 'unknown'}")

    net_result = run_command("virsh net-info default")
    lines.append("network: default")
    if net_result.returncode == 0:
        lines.extend(f"  {line}" for line in net_result.stdout.splitlines())
    else:
        lines.append(f"  unavailable: {net_result.stderr or net_result.stdout}")

    return "\n".join(lines)


def _vm_setup() -> str:
    """Enable virtualization support via Bazzite's official helper."""
    result = run_audited(
        "ujust setup-virtualization virt-on",
        tool="manage_vm",
        args={"action": "setup"},
    )
    if result.returncode != 0:
        raise ToolError(
            "Failed to run virtualization setup. "
            f"Output: {result.stderr or result.stdout}"
        )
    return (
        "Virtualization setup command completed. "
        "If libvirt access still fails, reboot and re-run status checks.\n\n"
        f"{result.stdout}"
    ).strip()


def _vm_list() -> str:
    """List known virtual machines."""
    result = run_command("virsh list --all")
    if result.returncode != 0:
        raise ToolError(f"Failed to list VMs: {result.stderr}")
    return result.stdout


def manage_vm(
    action: Literal[
        "setup",
        "status",
        "list",
        "create_default",
        "start",
        "stop",
        "delete",
        "snapshot_list",
        "snapshot_create",
        "snapshot_revert",
    ],
    name: str | None = None,
    iso_path: str | None = None,
    snapshot: str | None = None,
    ram_mb: int | None = None,
    vcpus: int | None = None,
    disk_gb: int | None = None,
    delete_storage: bool = False,
) -> str:
    """Manage VMs on Bazzite with hardened default profile support."""
    if action == "setup":
        return _vm_setup()
    if action == "status":
        return _vm_status()
    if action == "list":
        return _vm_list()
    if action == "create_default":
        if not name:
            raise ToolError("'name' is required for action='create_default'.")
        if not iso_path:
            raise ToolError("'iso_path' is required for action='create_default'.")
        return _create_default_vm(name, iso_path, ram_mb, vcpus, disk_gb)
    if action in ("start", "stop"):
        if not name:
            raise ToolError(f"'name' is required for action='{action}'.")
        return _vm_control(name, action)
    if action == "delete":
        if not name:
            raise ToolError("'name' is required for action='delete'.")
        return _vm_delete(name, delete_storage)
    if action == "snapshot_list":
        if not name:
            raise ToolError("'name' is required for action='snapshot_list'.")
        return _snapshot_list(name)
    if action == "snapshot_create":
        if not name:
            raise ToolError("'name' is required for action='snapshot_create'.")
        return _snapshot_create(name, snapshot)
    if action == "snapshot_revert":
        if not name:
            raise ToolError("'name' is required for action='snapshot_revert'.")
        if not snapshot:
            raise ToolError("'snapshot' is required for action='snapshot_revert'.")
        return _snapshot_revert(name, snapshot)
    raise ToolError(f"Unknown action '{action}'.")
