from __future__ import annotations

from typing import Literal

from bazzite_mcp.runner import ToolError, run_audited, run_command


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
    action: Literal["setup", "status", "list"],
) -> str:
    """Manage virtualization baseline operations on Bazzite."""
    if action == "setup":
        return _vm_setup()
    if action == "status":
        return _vm_status()
    if action == "list":
        return _vm_list()
    raise ToolError(f"Unknown action '{action}'.")
