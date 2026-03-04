from __future__ import annotations

import shlex
from typing import Literal

from bazzite_mcp.runner import ToolError, run_command


def system_info() -> str:
    """Get OS, kernel, desktop, and hardware summary."""
    commands = [
        ("OS", "cat /etc/os-release | grep -E '^(NAME|VERSION|VARIANT)=' | head -5"),
        ("Kernel", "uname -r"),
        ("Desktop", "echo $XDG_CURRENT_DESKTOP"),
        ("Session", "echo $XDG_SESSION_TYPE"),
        ("CPU", "lscpu | grep 'Model name' | head -1"),
        ("GPU", "lspci | grep -i 'vga\\|3d' | head -2"),
        ("RAM", "free -h | grep Mem | awk '{print $2}'"),
        ("Hostname", "hostname"),
    ]

    parts: list[str] = []
    for label, cmd in commands:
        result = run_command(cmd)
        parts.append(f"{label}: {result.stdout}")
    return "\n".join(parts)


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
    commands = [
        ("CPU", "lscpu | head -20"),
        ("GPU", "lspci -v | grep -A 10 -i 'vga\\|3d'"),
        ("Memory", "free -h"),
        ("Block Devices", "lsblk -o NAME,SIZE,TYPE,MOUNTPOINT"),
        ("Sensors", "sensors 2>/dev/null || echo 'sensors not available'"),
    ]

    parts: list[str] = []
    for label, cmd in commands:
        result = run_command(cmd)
        parts.append(f"=== {label} ===\n{result.stdout}")
    return "\n\n".join(parts)


def process_list(sort_by: Literal["cpu", "mem"] = "cpu", count: int = 15) -> str:
    """Show top processes sorted by cpu or memory usage."""
    sort_flag = "-%cpu" if sort_by == "cpu" else "-%mem"
    safe_count = max(1, min(count, 100))
    result = run_command(f"ps aux --sort={sort_flag} | head -n {safe_count + 1}")
    if result.returncode != 0:
        raise ToolError(f"Error: {result.stderr}")
    return result.stdout
