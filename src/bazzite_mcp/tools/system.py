from __future__ import annotations

import shlex
from typing import Literal

from bazzite_mcp.runner import ToolError, run_command


def _first_matching_line(text: str, needle: str) -> str:
    for line in text.splitlines():
        if needle.lower() in line.lower():
            return line.strip()
    return ""


def system_info() -> str:
    """Get OS, kernel, desktop, and hardware summary."""
    os_result = run_command("cat /etc/os-release")
    os_lines = [
        line
        for line in os_result.stdout.splitlines()
        if line.startswith(("NAME=", "VERSION=", "VARIANT="))
    ]
    os_summary = "\n".join(os_lines[:5]) if os_lines else os_result.stdout

    kernel_result = run_command("uname -r")
    desktop_result = run_command("echo $XDG_CURRENT_DESKTOP")
    session_result = run_command("echo $XDG_SESSION_TYPE")

    lscpu_result = run_command("lscpu")
    cpu_model = _first_matching_line(lscpu_result.stdout, "model name")

    lspci_result = run_command("lspci")
    gpu_lines = [
        line
        for line in lspci_result.stdout.splitlines()
        if "vga" in line.lower() or "3d" in line.lower()
    ]
    gpu_summary = "\n".join(gpu_lines[:2]) if gpu_lines else lspci_result.stdout

    free_result = run_command("free -h")
    mem_line = _first_matching_line(free_result.stdout, "Mem:")
    mem_total = mem_line.split()[1] if mem_line else free_result.stdout

    hostname_result = run_command("hostname")

    return "\n".join(
        [
            f"OS: {os_summary}",
            f"Kernel: {kernel_result.stdout}",
            f"Desktop: {desktop_result.stdout}",
            f"Session: {session_result.stdout}",
            f"CPU: {cpu_model}",
            f"GPU: {gpu_summary}",
            f"RAM: {mem_total}",
            f"Hostname: {hostname_result.stdout}",
        ]
    )


def disk_usage() -> str:
    """Show disk space by mount point."""
    result = run_command(
        "df -h --output=source,size,used,avail,pcent,target -x tmpfs -x devtmpfs -x squashfs"
    )
    if result.returncode != 0:
        raise ToolError(f"Error: {result.stderr}")
    return result.stdout


def update_status() -> str:
    """Check OS update status via rpm-ostree."""
    result = run_command("rpm-ostree status")
    if result.returncode != 0:
        raise ToolError(f"Error: {result.stderr}")
    return result.stdout


def journal_logs(
    unit: str | None = None,
    priority: str | None = None,
    since: str | None = None,
    lines: int = 50,
) -> str:
    """Query journalctl with optional filters."""
    cmd = f"journalctl --no-pager -n {lines}"
    if unit:
        cmd += f" -u {shlex.quote(unit)}"
    if priority:
        cmd += f" -p {shlex.quote(priority)}"
    if since:
        cmd += f" --since {shlex.quote(since)}"

    result = run_command(cmd)
    if result.returncode != 0:
        raise ToolError(f"Error: {result.stderr}")
    return result.stdout


def hardware_info() -> str:
    """Get a broader hardware report."""
    lscpu_result = run_command("lscpu")
    cpu_output = "\n".join(lscpu_result.stdout.splitlines()[:20])

    lspci_result = run_command("lspci -v")
    lspci_lines = lspci_result.stdout.splitlines()
    gpu_output = ""
    for index, line in enumerate(lspci_lines):
        lowered = line.lower()
        if "vga" in lowered or "3d" in lowered:
            gpu_output = "\n".join(lspci_lines[index : index + 11])
            break
    if not gpu_output:
        gpu_output = lspci_result.stdout

    memory_result = run_command("free -h")
    block_result = run_command("lsblk -o NAME,SIZE,TYPE,MOUNTPOINT")
    sensors_result = run_command("sensors")
    sensors_output = (
        sensors_result.stdout
        if sensors_result.returncode == 0
        else "sensors not available"
    )

    parts: list[str] = [
        f"=== CPU ===\n{cpu_output}",
        f"=== GPU ===\n{gpu_output}",
        f"=== Memory ===\n{memory_result.stdout}",
        f"=== Block Devices ===\n{block_result.stdout}",
        f"=== Sensors ===\n{sensors_output}",
    ]
    return "\n\n".join(parts)


def process_list(sort_by: Literal["cpu", "mem"] = "cpu", count: int = 15) -> str:
    """Show top processes sorted by cpu or memory usage."""
    sort_flag = "-%cpu" if sort_by == "cpu" else "-%mem"
    safe_count = max(1, min(count, 100))
    result = run_command(f"ps aux --sort={sort_flag}")
    if result.returncode != 0:
        raise ToolError(f"Error: {result.stderr}")
    lines = result.stdout.splitlines()
    return "\n".join(lines[: safe_count + 1])
