from __future__ import annotations

import shlex
from typing import Literal

from bazzite_mcp.runner import ToolError, run_audited, run_command


def _service_status(name: str, user: bool = False) -> str:
    """Get status of a systemd service."""
    scope = "--user" if user else ""
    result = run_command(f"systemctl {scope} status {shlex.quote(name)} --no-pager")
    return result.stdout if result.stdout else result.stderr


def _list_services(
    state: str | None = None,
    user: bool = False,
) -> str:
    """List systemd services, optionally filtered by state."""
    scope = "--user" if user else ""
    if state in ("running", "failed"):
        result = run_command(
            f"systemctl {scope} list-units --type=service --state={shlex.quote(state)} --no-pager"
        )
    elif state in ("enabled", "disabled"):
        result = run_command(
            f"systemctl {scope} list-unit-files --type=service --state={shlex.quote(state)} --no-pager"
        )
    else:
        result = run_command(f"systemctl {scope} list-units --type=service --no-pager")
    return result.stdout


def _network_status() -> str:
    """Show NetworkManager connections, interfaces, and IP info."""
    parts: list[str] = []

    result = run_command("nmcli general status")
    parts.append(f"=== General ===\n{result.stdout}")

    result = run_command("nmcli connection show --active")
    parts.append(f"=== Active Connections ===\n{result.stdout}")

    result = run_command("ip -brief addr show")
    parts.append(f"=== IP Addresses ===\n{result.stdout}")

    return "\n\n".join(parts)


def _manage_connection(
    action: str,
    name: str | None = None,
    properties: str | None = None,
) -> str:
    """Create, modify, or delete NetworkManager connections."""
    if action == "show":
        result = run_command("nmcli connection show")
    elif action in ("up", "down", "delete") and name:
        result = run_audited(
            f"nmcli connection {action} {shlex.quote(name)}",
            tool="manage_network",
            args={"action": action, "name": name},
        )
    elif action == "modify" and name and properties:
        try:
            prop_parts = shlex.split(properties)
        except ValueError:
            raise ToolError("Invalid properties syntax.")
        safe_props = " ".join(shlex.quote(p) for p in prop_parts)
        result = run_audited(
            f"nmcli connection modify {shlex.quote(name)} {safe_props}",
            tool="manage_network",
            args={"action": action, "name": name, "properties": properties},
        )
    else:
        raise ToolError(
            "Usage: action='show|up|down|delete|modify', name=<connection>, properties=<nmcli args for modify>"
        )

    if result.returncode != 0:
        raise ToolError(f"Error: {result.stderr}")
    return result.stdout


def manage_service(
    name: str | None = None,
    action: Literal[
        "start", "stop", "restart", "enable", "disable",
        "enable --now", "disable --now", "status", "list"
    ] = "status",
    user: bool = False,
    state: Literal["running", "failed", "enabled", "disabled"] | None = None,
) -> str:
    """Manage systemd services: start/stop/restart/enable/disable, get status, or list."""
    if action == "status":
        if not name:
            raise ToolError("'name' is required for action='status'.")
        return _service_status(name, user)
    if action == "list":
        return _list_services(state, user)

    # Mutation actions require a name
    if not name:
        raise ToolError(f"'name' is required for action='{action}'.")

    scope = "--user" if user else ""
    sname = shlex.quote(name)
    reverse = {
        "start": "stop",
        "stop": "start",
        "enable": "disable",
        "disable": "enable",
        "enable --now": "disable --now",
        "disable --now": "enable --now",
    }.get(action)
    rollback_cmd = f"systemctl {scope} {reverse} {sname}" if reverse else None
    result = run_audited(
        f"systemctl {scope} {action} {sname}",
        tool="manage_service",
        args={"name": name, "action": action, "user": user},
        rollback=rollback_cmd,
    )
    if result.returncode != 0:
        raise ToolError(f"Failed to {action} {name}: {result.stderr}")
    return f"Service '{name}' {action} successful."


def manage_firewall(
    action: Literal["list", "add-port", "remove-port", "add-service", "remove-service"],
    port: str | None = None,
    service: str | None = None,
) -> str:
    """Manage firewalld rules with audit logging and auto-reload."""
    if action == "list":
        result = run_command("firewall-cmd --list-all")
        if result.returncode != 0:
            raise ToolError(f"Error: {result.stderr}")
        return result.stdout

    primary_cmd = ""
    rollback_cmd = ""
    if action == "add-port" and port:
        sport = shlex.quote(port)
        primary_cmd = f"pkexec firewall-cmd --add-port={sport} --permanent"
        rollback_cmd = f"pkexec firewall-cmd --remove-port={sport} --permanent"
    elif action == "remove-port" and port:
        sport = shlex.quote(port)
        primary_cmd = f"pkexec firewall-cmd --remove-port={sport} --permanent"
        rollback_cmd = f"pkexec firewall-cmd --add-port={sport} --permanent"
    elif action == "add-service" and service:
        ssvc = shlex.quote(service)
        primary_cmd = f"pkexec firewall-cmd --add-service={ssvc} --permanent"
        rollback_cmd = f"pkexec firewall-cmd --remove-service={ssvc} --permanent"
    elif action == "remove-service" and service:
        ssvc = shlex.quote(service)
        primary_cmd = f"pkexec firewall-cmd --remove-service={ssvc} --permanent"
        rollback_cmd = f"pkexec firewall-cmd --add-service={ssvc} --permanent"
    else:
        raise ToolError(
            "Usage: action='list|add-port|remove-port|add-service|remove-service'"
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


def manage_network(
    action: Literal["status", "show", "up", "down", "delete", "modify"],
    name: str | None = None,
    properties: str | None = None,
) -> str:
    """Manage NetworkManager connections and view network status."""
    if action == "status":
        return _network_status()
    return _manage_connection(action, name, properties)
