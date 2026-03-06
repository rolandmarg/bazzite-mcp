from __future__ import annotations

import os
from typing import Literal

from bazzite_mcp.runner import run_command


def _first_matching_line(text: str, needle: str) -> str:
    for line in text.splitlines():
        if needle.lower() in line.lower():
            return line.strip()
    return ""


def _system_info_basic() -> str:
    """Get OS, kernel, desktop, and hardware summary."""
    os_result = run_command(["cat", "/etc/os-release"])
    os_lines = [
        line
        for line in os_result.stdout.splitlines()
        if line.startswith(("NAME=", "VERSION=", "VARIANT="))
    ]
    os_summary = "\n".join(os_lines[:5]) if os_lines else os_result.stdout

    kernel_result = run_command(["uname", "-r"])
    desktop_value = os.environ.get("XDG_CURRENT_DESKTOP", "")
    session_value = os.environ.get("XDG_SESSION_TYPE", "")

    lscpu_result = run_command(["lscpu"])
    cpu_model = _first_matching_line(lscpu_result.stdout, "model name")

    lspci_result = run_command(["lspci"])
    gpu_lines = [
        line
        for line in lspci_result.stdout.splitlines()
        if "vga" in line.lower() or "3d controller" in line.lower()
    ]
    gpu_summary = "\n".join(gpu_lines[:2]) if gpu_lines else lspci_result.stdout

    free_result = run_command(["free", "-h"])
    mem_line = _first_matching_line(free_result.stdout, "Mem:")
    mem_total = mem_line.split()[1] if mem_line else free_result.stdout

    hostname_result = run_command(["hostname"])

    return "\n".join(
        [
            f"OS: {os_summary}",
            f"Kernel: {kernel_result.stdout}",
            f"Desktop: {desktop_value}",
            f"Session: {session_value}",
            f"CPU: {cpu_model}",
            f"GPU: {gpu_summary}",
            f"RAM: {mem_total}",
            f"Hostname: {hostname_result.stdout}",
        ]
    )


def _hardware_info() -> str:
    """Get a broader hardware report."""
    lscpu_result = run_command(["lscpu"])
    cpu_output = "\n".join(lscpu_result.stdout.splitlines()[:20])

    lspci_result = run_command(["lspci", "-v"])
    lspci_lines = lspci_result.stdout.splitlines()
    gpu_output = ""
    for index, line in enumerate(lspci_lines):
        lowered = line.lower()
        if "vga" in lowered or "3d controller" in lowered:
            gpu_output = "\n".join(lspci_lines[index : index + 11])
            break
    if not gpu_output:
        gpu_output = lspci_result.stdout

    memory_result = run_command(["free", "-h"])
    block_result = run_command(["lsblk", "-o", "NAME,SIZE,TYPE,MOUNTPOINT"])
    sensors_result = run_command(["sensors"])
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


def system_info(detail: Literal["basic", "full"] = "basic") -> str:
    """Get system info: basic summary or full hardware report."""
    if detail == "full":
        return _hardware_info()
    return _system_info_basic()
