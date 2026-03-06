from __future__ import annotations

import re
from typing import Literal

from bazzite_mcp.runner import ToolError, run_audited, run_command

_PORT_RE = re.compile(r"^\d+(?:-\d+)?/(tcp|udp)$")
_SERVICE_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def manage_firewall(
    action: Literal["list", "add_port", "remove_port", "add_service", "remove_service"],
    port: str | None = None,
    service: str | None = None,
) -> str:
    """Manage firewalld rules with audit logging and reload."""
    if action == "list":
        result = run_command(["firewall-cmd", "--list-all"])
        if result.returncode != 0:
            raise ToolError(f"Error: {result.stderr}")
        return result.stdout

    primary_cmd: list[str] | None = None
    rollback_cmd: list[str] | None = None
    if action == "add_port" and port:
        if not _PORT_RE.match(port):
            raise ToolError(f"Invalid port spec '{port}'. Use forms like 8080/tcp.")
        primary_cmd = ["pkexec", "firewall-cmd", f"--add-port={port}", "--permanent"]
        rollback_cmd = ["pkexec", "firewall-cmd", f"--remove-port={port}", "--permanent"]
    elif action == "remove_port" and port:
        if not _PORT_RE.match(port):
            raise ToolError(f"Invalid port spec '{port}'. Use forms like 8080/tcp.")
        primary_cmd = ["pkexec", "firewall-cmd", f"--remove-port={port}", "--permanent"]
        rollback_cmd = ["pkexec", "firewall-cmd", f"--add-port={port}", "--permanent"]
    elif action == "add_service" and service:
        if not _SERVICE_RE.match(service):
            raise ToolError(f"Invalid service name '{service}'.")
        primary_cmd = ["pkexec", "firewall-cmd", f"--add-service={service}", "--permanent"]
        rollback_cmd = ["pkexec", "firewall-cmd", f"--remove-service={service}", "--permanent"]
    elif action == "remove_service" and service:
        if not _SERVICE_RE.match(service):
            raise ToolError(f"Invalid service name '{service}'.")
        primary_cmd = ["pkexec", "firewall-cmd", f"--remove-service={service}", "--permanent"]
        rollback_cmd = ["pkexec", "firewall-cmd", f"--add-service={service}", "--permanent"]
    else:
        raise ToolError(
            "Usage: action='list|add_port|remove_port|add_service|remove_service'"
        )

    change_result = run_audited(
        primary_cmd,
        tool="manage_firewall",
        args={"action": action, "port": port, "service": service},
        rollback=rollback_cmd,
    )
    if change_result.returncode != 0:
        raise ToolError(f"Error: {change_result.stderr}")

    reload_result = run_audited(
        ["pkexec", "firewall-cmd", "--reload"],
        tool="manage_firewall",
        args={"action": "reload", "triggered_by": action},
    )
    if reload_result.returncode != 0:
        raise ToolError(f"Firewall updated but reload failed: {reload_result.stderr}")

    out = change_result.stdout.strip()
    reload_out = reload_result.stdout.strip()
    if out and reload_out:
        return f"{out}\n{reload_out}"
    return out or reload_out or "Firewall updated and reloaded."
