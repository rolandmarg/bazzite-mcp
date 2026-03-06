from __future__ import annotations

import os
import re
from pathlib import Path

from bazzite_mcp.runner import ToolError, run_command

from .shared import _resolve_iso_path


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
