from __future__ import annotations

import json
import os
import re
import shlex
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from bazzite_mcp.runner import ToolError, run_audited, run_command


VM_STORAGE_DIR = Path.home() / ".local" / "share" / "bazzite-mcp" / "vms"
VM_OPERATION_STATE_FILE = VM_STORAGE_DIR.parent / "vm_operation_state.json"
DEFAULT_DISK_GB = 64


@dataclass(frozen=True)
class AtomicStep:
    label: str
    command: str
    rollback: str | None = None
    rollback_on_failure: bool = False


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _save_operation_state(state: dict[str, Any]) -> None:
    VM_OPERATION_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {**state, "updated_at": _utc_timestamp()}
    VM_OPERATION_STATE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load_operation_state() -> dict[str, Any] | None:
    if not VM_OPERATION_STATE_FILE.exists():
        return None
    try:
        return json.loads(VM_OPERATION_STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {
            "operation": "unknown",
            "state": "failed",
            "error": f"Corrupt operation state file: {VM_OPERATION_STATE_FILE}",
            "updated_at": _utc_timestamp(),
        }


def _format_operation_state() -> list[str]:
    state = _load_operation_state()
    if not state:
        return ["operation", "  state: none"]

    lines = ["operation"]
    lines.append(f"  action: {state.get('operation', 'unknown')}")
    lines.append(f"  state:  {state.get('state', 'unknown')}")
    updated_at = state.get("updated_at")
    if updated_at:
        lines.append(f"  updated: {updated_at}")

    for change in state.get("applied_changes", []):
        lines.append(f"  applied: {change}")

    for warning in state.get("warnings", []):
        lines.append(f"  warning: {warning}")

    error = state.get("error")
    if error:
        lines.append(f"  error: {error}")

    return lines


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


def _collect_vm_preflight(
    iso_path: str | None = None,
    require_iommu: bool = False,
) -> dict[str, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []

    cpu_result = run_command("lscpu")
    if cpu_result.returncode != 0:
        warnings.append("lscpu unavailable; could not verify virtualization capability")
    else:
        virt_lines = [
            line.strip()
            for line in cpu_result.stdout.splitlines()
            if "virtualization" in line.lower()
        ]
        if virt_lines:
            info.extend(virt_lines)
        else:
            errors.append(
                "missing_virtualization: CPU virtualization capability not reported by lscpu"
            )

    virt_install_result = run_command("virt-install --version")
    if virt_install_result.returncode != 0:
        errors.append(
            "missing_dependency: virt-install is unavailable; install virtualization prerequisites first"
        )

    virsh_result = run_command("virsh --version")
    if virsh_result.returncode != 0:
        errors.append("missing_dependency: virsh is unavailable")

    enabled_result = run_command("systemctl is-enabled libvirtd")
    enabled_value = enabled_result.stdout.strip()
    if enabled_result.returncode != 0 or enabled_value != "enabled":
        errors.append(
            "service_disabled: libvirtd is not enabled; run manage_vm(action='prepare')"
        )

    active_result = run_command("systemctl is-active libvirtd")
    active_value = active_result.stdout.strip()
    if active_result.returncode != 0 or active_value != "active":
        warnings.append(
            "service_inactive: libvirtd is not active yet (this is expected before reboot in some setups)"
        )

    net_result = run_command("virsh net-info default")
    if net_result.returncode != 0:
        errors.append("network_missing: libvirt default network is unavailable")

    gpu_result = run_command("lspci")
    if gpu_result.returncode == 0:
        gpu_lines = [
            line
            for line in gpu_result.stdout.splitlines()
            if re.search(r"(VGA compatible controller|3D controller)", line)
        ]
        if len(gpu_lines) <= 1:
            warnings.append(
                "single_gpu_host: GPU passthrough is risky on single-GPU systems"
            )
        else:
            info.append(f"Detected {len(gpu_lines)} display-class GPUs")

    try:
        cmdline = Path("/proc/cmdline").read_text(encoding="utf-8")
    except OSError:
        cmdline = ""
    iommu_enabled = bool(
        re.search(r"\b(intel_iommu|amd_iommu)=on\b", cmdline)
        or re.search(r"\biommu=pt\b", cmdline)
    )
    if require_iommu and not iommu_enabled:
        errors.append("iommu_disabled: IOMMU kernel arguments are not enabled")
    elif not iommu_enabled:
        warnings.append(
            "iommu_disabled: passthrough will require IOMMU kernel arguments"
        )

    if iso_path:
        try:
            iso = _resolve_iso_path(iso_path)
            info.append(f"ISO ok: {iso}")
        except ToolError as exc:
            errors.append(f"invalid_iso: {exc}")

    return {"errors": errors, "warnings": warnings, "info": info}


def _format_preflight_report(report: dict[str, list[str]]) -> str:
    ready = "yes" if not report["errors"] else "no"
    lines = ["VM preflight", f"ready: {ready}"]

    for info in report["info"]:
        lines.append(f"info: {info}")
    for warning in report["warnings"]:
        lines.append(f"warning: {warning}")
    for error in report["errors"]:
        lines.append(f"error: {error}")

    return "\n".join(lines)


def _assert_create_preflight(iso_path: str) -> None:
    report = _collect_vm_preflight(iso_path=iso_path, require_iommu=False)
    if report["errors"]:
        raise ToolError(
            "preflight_failed: VM creation blocked until preflight passes.\n"
            + _format_preflight_report(report)
        )


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

    steps = [
        AtomicStep(
            label="create_vm",
            command=cmd,
            rollback=f"virsh undefine {sname} --nvram --remove-all-storage",
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

    lines.extend(_format_operation_state())

    return "\n".join(lines)


def _vm_preflight(iso_path: str | None = None, require_iommu: bool = False) -> str:
    """Run readiness checks without mutating host state."""
    report = _collect_vm_preflight(iso_path=iso_path, require_iommu=require_iommu)
    return _format_preflight_report(report)


def _has_pending_deployment() -> bool:
    status_result = run_command("rpm-ostree status")
    if status_result.returncode != 0:
        return False

    lines = status_result.stdout.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == "Deployments:" and index + 1 < len(lines):
            first_deployment = lines[index + 1].lstrip()
            return not first_deployment.startswith("●")
    return False


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


def _vm_rollback() -> str:
    """Rollback the last prepare operation, if present."""
    state = _load_operation_state()
    if not state:
        return "No VM operation state found. Nothing to roll back."

    rollback_steps = state.get("rollback_steps") or []
    if not rollback_steps:
        return "No rollback steps recorded for the last VM operation."

    failures: list[str] = []
    for step in reversed(rollback_steps):
        label = str(step.get("label", "rollback_step"))
        command = str(step.get("command", "")).strip()
        if not command:
            continue
        result = run_audited(
            command,
            tool="manage_vm",
            args={"action": "rollback", "step": label},
        )
        if result.returncode != 0:
            failures.append(f"{label}: {result.stderr or result.stdout}")

    if failures:
        _save_operation_state(
            {
                **state,
                "state": "failed",
                "error": "Rollback failed: " + "; ".join(failures),
            }
        )
        raise ToolError("rollback_failed: " + "; ".join(failures))

    _save_operation_state(
        {
            **state,
            "state": "rolled_back",
            "applied_changes": [],
            "warnings": [],
            "error": None,
        }
    )
    return "Rollback completed. VM preparation changes were reverted."


def _vm_setup() -> str:
    """Compatibility alias for prepare."""
    return _vm_prepare()


def _vm_list() -> str:
    """List known virtual machines."""
    result = run_command("virsh list --all")
    if result.returncode != 0:
        raise ToolError(f"Failed to list VMs: {result.stderr}")
    return result.stdout


def manage_vm(
    action: Literal[
        "setup",
        "prepare",
        "preflight",
        "rollback",
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
    require_iommu: bool = False,
) -> str:
    """Manage VMs on Bazzite with hardened default profile support."""
    if action == "prepare":
        return _vm_prepare()
    if action == "preflight":
        return _vm_preflight(iso_path=iso_path, require_iommu=require_iommu)
    if action == "rollback":
        return _vm_rollback()
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
