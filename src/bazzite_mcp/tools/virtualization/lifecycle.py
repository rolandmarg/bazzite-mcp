from __future__ import annotations

import shlex
from datetime import datetime
from typing import Any, Literal

from bazzite_mcp.runner import ToolError, run_audited, run_command

from .preflight import (
    _assert_create_preflight,
    _collect_vm_preflight,
    _default_ram_mb,
    _default_vcpus,
    _format_preflight_report,
    _has_pending_deployment,
    _host_resources,
)
from .shared import (
    DEFAULT_DISK_GB,
    VM_STORAGE_DIR,
    AtomicStep,
    _resolve_iso_path,
    _validate_vm_name,
)
from .state import _format_operation_state, _save_operation_state


def _run_atomic_steps(
    operation: str,
    steps: list[AtomicStep],
    base_args: dict[str, Any],
) -> list[str]:
    applied: list[AtomicStep] = []

    for step in steps:
        args = {**base_args, "operation": operation, "step": step.label}
        result = run_audited(
            step.command,
            tool="manage_vm",
            args=args,
            rollback=step.rollback,
        )
        if result.returncode == 0:
            applied.append(step)
            continue

        rollback_results: list[str] = []

        if step.rollback and step.rollback_on_failure:
            current_rollback = run_audited(
                step.rollback,
                tool="manage_vm",
                args={**args, "action": "atomic_rollback", "failed_step": step.label},
            )
            status = "ok" if current_rollback.returncode == 0 else "failed"
            rollback_results.append(f"{step.label}: {status}")

        for previous in reversed(applied):
            if not previous.rollback:
                continue
            previous_rollback = run_audited(
                previous.rollback,
                tool="manage_vm",
                args={
                    **base_args,
                    "operation": operation,
                    "action": "atomic_rollback",
                    "step": previous.label,
                },
            )
            status = "ok" if previous_rollback.returncode == 0 else "failed"
            rollback_results.append(f"{previous.label}: {status}")

        failure_output = result.stderr or result.stdout or "unknown error"
        rollback_summary = (
            "\nRollback: " + ", ".join(rollback_results)
            if rollback_results
            else "\nRollback: no rollback steps available"
        )
        raise ToolError(
            f"Atomic operation '{operation}' failed at step '{step.label}': {failure_output}"
            f"{rollback_summary}"
        )

    return [step.label for step in applied]


def _create_default_vm(
    name: str,
    iso_path: str,
    ram_mb: int | None = None,
    vcpus: int | None = None,
    disk_gb: int | None = None,
) -> str:
    """Create a Windows-focused low-overhead VM profile for untrusted binaries."""
    _validate_vm_name(name)
    _assert_create_preflight(iso_path)
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

    quoted_name = shlex.quote(name)
    quoted_iso = shlex.quote(str(iso))
    disk_spec = shlex.quote(
        f"path={disk_path},size={effective_disk},format=qcow2,bus=sata"
    )
    cmd = (
        f"virt-install --name {quoted_name} --memory {effective_ram} --vcpus {effective_vcpus} "
        "--cpu host-passthrough --machine q35 --os-variant win10 "
        f"--disk {disk_spec} --cdrom {quoted_iso} "
        "--network network=default,model=e1000 "
        "--graphics spice --video qxl --channel spicevmc "
        "--noautoconsole --wait 0"
    )

    steps = [
        AtomicStep(
            label="create_vm",
            command=cmd,
            rollback=f"virsh undefine {quoted_name} --nvram --remove-all-storage",
            rollback_on_failure=True,
        )
    ]
    _run_atomic_steps(
        operation="create_default",
        steps=steps,
        base_args={
            "action": "create_default",
            "name": name,
            "iso_path": str(iso),
            "ram_mb": effective_ram,
            "vcpus": effective_vcpus,
            "disk_gb": effective_disk,
            "profile": "windows-untrusted-lite",
        },
    )

    return (
        f"Created VM '{name}' (windows-untrusted-lite).\n"
        f"RAM={effective_ram}MB, vCPUs={effective_vcpus}, disk={effective_disk}GB\n"
        f"ISO={iso}"
    )


def _vm_control(name: str, action: Literal["start", "stop"]) -> str:
    """Start or stop a VM."""
    _validate_vm_name(name)
    quoted_name = shlex.quote(name)
    cmd = "virsh start" if action == "start" else "virsh shutdown"
    result = run_audited(
        f"{cmd} {quoted_name}",
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
    quoted_name = shlex.quote(name)

    state_result = run_command(f"virsh domstate {quoted_name}")
    if state_result.returncode == 0 and "running" in state_result.stdout.lower():
        raise ToolError(
            f"VM '{name}' is running. Stop it first with manage_vm(action='stop', name='{name}')."
        )

    cmd = f"virsh undefine {quoted_name} --nvram"
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

    lines.extend(_format_operation_state())

    return "\n".join(lines)


def _vm_preflight(iso_path: str | None = None, require_iommu: bool = False) -> str:
    """Run readiness checks without mutating host state."""
    report = _collect_vm_preflight(iso_path=iso_path, require_iommu=require_iommu)
    return _format_preflight_report(report)


def _vm_prepare() -> str:
    """Enable virtualization using an atomic, rollback-capable operation."""
    rollback_steps = [
        {
            "label": "disable_virtualization",
            "command": "ujust setup-virtualization virt-off",
        }
    ]
    _save_operation_state(
        {
            "operation": "prepare",
            "state": "in_progress",
            "applied_changes": [],
            "rollback_steps": rollback_steps,
        }
    )

    try:
        applied_changes = _run_atomic_steps(
            operation="prepare",
            steps=[
                AtomicStep(
                    label="enable_virtualization",
                    command="ujust setup-virtualization virt-on",
                    rollback="ujust setup-virtualization virt-off",
                )
            ],
            base_args={"action": "prepare"},
        )
    except ToolError as exc:
        _save_operation_state(
            {
                "operation": "prepare",
                "state": "failed",
                "applied_changes": [],
                "rollback_steps": rollback_steps,
                "error": str(exc),
            }
        )
        raise

    warnings: list[str] = []
    if _has_pending_deployment():
        state = "reboot_required"
        warnings.append(
            "A reboot is required to finish applying pending deployment changes"
        )
    else:
        state = "applied"

    if run_command("virt-install --version").returncode != 0:
        warnings.append(
            "virt-install is still unavailable; preflight will fail for VM creation"
        )

    _save_operation_state(
        {
            "operation": "prepare",
            "state": state,
            "applied_changes": applied_changes,
            "rollback_steps": rollback_steps,
            "warnings": warnings,
        }
    )

    lines = [
        "Virtualization prepare completed (atomic).",
        f"state: {state}",
        "Use manage_vm(action='rollback') to undo this preparation.",
    ]
    for warning in warnings:
        lines.append(f"warning: {warning}")
    return "\n".join(lines)


def _vm_setup() -> str:
    """Compatibility alias for prepare."""
    return _vm_prepare()


def _vm_list() -> str:
    """List known virtual machines."""
    result = run_command("virsh list --all")
    if result.returncode != 0:
        raise ToolError(f"Failed to list VMs: {result.stderr}")
    return result.stdout
