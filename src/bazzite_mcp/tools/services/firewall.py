from __future__ import annotations

import shlex
from typing import Literal

from bazzite_mcp.runner import ToolError, run_audited, run_command


def manage_firewall(
    action: Literal["list", "add_port", "remove_port", "add_service", "remove_service"],
    port: str | None = None,
    service: str | None = None,
) -> str:
    """Manage firewalld rules with audit logging and reload."""
    if action == "list":
        result = run_command("firewall-cmd --list-all")
        if result.returncode != 0:
            raise ToolError(f"Error: {result.stderr}")
        return result.stdout

    primary_cmd = ""
    rollback_cmd = ""
    if action == "add_port" and port:
        sport = shlex.quote(port)
        primary_cmd = f"pkexec firewall-cmd --add-port={sport} --permanent"
        rollback_cmd = f"pkexec firewall-cmd --remove-port={sport} --permanent"
    elif action == "remove_port" and port:
        sport = shlex.quote(port)
        primary_cmd = f"pkexec firewall-cmd --remove-port={sport} --permanent"
        rollback_cmd = f"pkexec firewall-cmd --add-port={sport} --permanent"
    elif action == "add_service" and service:
        ssvc = shlex.quote(service)
        primary_cmd = f"pkexec firewall-cmd --add-service={ssvc} --permanent"
        rollback_cmd = f"pkexec firewall-cmd --remove-service={ssvc} --permanent"
    elif action == "remove_service" and service:
        ssvc = shlex.quote(service)
        primary_cmd = f"pkexec firewall-cmd --remove-service={ssvc} --permanent"
        rollback_cmd = f"pkexec firewall-cmd --add-service={ssvc} --permanent"
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
        "pkexec firewall-cmd --reload",
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
