from __future__ import annotations

import shlex
from typing import Literal

from bazzite_mcp.runner import run_audited, run_command


def manage_service(
    name: str,
    action: Literal["start", "stop", "restart", "enable", "disable", "enable --now", "disable --now"],
    user: bool = False,
) -> str:
    """Start, stop, restart, enable, or disable a systemd service."""
    valid_actions = ("start", "stop", "restart", "enable", "disable", "enable --now", "disable --now")
    if action not in valid_actions:
        return f"Unknown action '{action}'. Supported: {', '.join(valid_actions)}."

    scope = "--user" if user else ""
    sname = shlex.quote(name)
    # Determine rollback action
    reverse = {"start": "stop", "stop": "start", "enable": "disable", "disable": "enable",
                "enable --now": "disable --now", "disable --now": "enable --now"}.get(action)
    rollback_cmd = f"systemctl {scope} {reverse} {sname}" if reverse else None
    result = run_audited(
        f"systemctl {scope} {action} {sname}",
        tool="manage_service",
        args={"name": name, "action": action, "user": user},
        rollback=rollback_cmd,
    )
    if result.returncode != 0:
        return f"Failed to {action} {name}: {result.stderr}"
    return f"Service '{name}' {action} successful."


def service_status(name: str, user: bool = False) -> str:
    """Get status of a systemd service."""
    scope = "--user" if user else ""
    result = run_command(f"systemctl {scope} status {shlex.quote(name)} --no-pager")
    return result.stdout if result.stdout else result.stderr


def list_services(
    state: Literal["running", "failed", "enabled", "disabled"] | None = None,
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


def network_status() -> str:
    """Show NetworkManager connections, interfaces, and IP info."""
    parts: list[str] = []

    result = run_command("nmcli general status")
    parts.append(f"=== General ===\n{result.stdout}")

    result = run_command("nmcli connection show --active")
    parts.append(f"=== Active Connections ===\n{result.stdout}")

    result = run_command("ip -brief addr show")
    parts.append(f"=== IP Addresses ===\n{result.stdout}")

    return "\n\n".join(parts)


def manage_connection(
    action: Literal["show", "up", "down", "delete", "modify"],
    name: str | None = None,
    properties: str | None = None,
) -> str:
    """Create, modify, or delete NetworkManager connections.

    Use 'show' to list all connections, 'up'/'down' to activate/deactivate.
    For 'modify', provide properties as space-separated key=value pairs
    (e.g. 'ipv4.dns 8.8.8.8').
    """
    if action == "show":
        result = run_command("nmcli connection show")
    elif action in ("up", "down", "delete") and name:
        result = run_audited(
            f"nmcli connection {action} {shlex.quote(name)}",
            tool="manage_connection",
            args={"action": action, "name": name},
        )
    elif action == "modify" and name and properties:
        # Sanitize properties: split and re-quote each token
        try:
            prop_parts = shlex.split(properties)
        except ValueError:
            return "Invalid properties syntax."
        safe_props = " ".join(shlex.quote(p) for p in prop_parts)
        result = run_audited(
            f"nmcli connection modify {shlex.quote(name)} {safe_props}",
            tool="manage_connection",
            args={"action": action, "name": name, "properties": properties},
        )
    else:
        return "Usage: action='show|up|down|delete|modify', name=<connection>, properties=<nmcli args for modify>"

    return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"


def manage_firewall(
    action: Literal["list", "add-port", "remove-port", "add-service", "remove-service"],
    port: str | None = None,
    service: str | None = None,
) -> str:
    """Manage firewalld rules.

    Use 'list' to see current rules. Use 'add-port'/'remove-port' with a port
    string like '8080/tcp'. Use 'add-service'/'remove-service' with a service name.
    """
    if action == "list":
        result = run_command("firewall-cmd --list-all")
    elif action == "add-port" and port:
        sport = shlex.quote(port)
        result = run_audited(
            f"pkexec firewall-cmd --add-port={sport} --permanent && pkexec firewall-cmd --reload",
            tool="manage_firewall",
            args={"action": action, "port": port},
            rollback=f"pkexec firewall-cmd --remove-port={sport} --permanent && pkexec firewall-cmd --reload",
        )
    elif action == "remove-port" and port:
        sport = shlex.quote(port)
        result = run_audited(
            f"pkexec firewall-cmd --remove-port={sport} --permanent && pkexec firewall-cmd --reload",
            tool="manage_firewall",
            args={"action": action, "port": port},
            rollback=f"pkexec firewall-cmd --add-port={sport} --permanent && pkexec firewall-cmd --reload",
        )
    elif action == "add-service" and service:
        ssvc = shlex.quote(service)
        result = run_audited(
            f"pkexec firewall-cmd --add-service={ssvc} --permanent && pkexec firewall-cmd --reload",
            tool="manage_firewall",
            args={"action": action, "service": service},
            rollback=f"pkexec firewall-cmd --remove-service={ssvc} --permanent && pkexec firewall-cmd --reload",
        )
    elif action == "remove-service" and service:
        ssvc = shlex.quote(service)
        result = run_audited(
            f"pkexec firewall-cmd --remove-service={ssvc} --permanent && pkexec firewall-cmd --reload",
            tool="manage_firewall",
            args={"action": action, "service": service},
            rollback=f"pkexec firewall-cmd --add-service={ssvc} --permanent && pkexec firewall-cmd --reload",
        )
    else:
        return "Usage: action='list|add-port|remove-port|add-service|remove-service'"

    return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"


def manage_tailscale(action: Literal["status", "up", "down", "ip", "peers"]) -> str:
    """Manage Tailscale VPN. Use 'status' or 'peers' to check state, 'up'/'down' to toggle."""

    if action == "peers":
        result = run_command("tailscale status")
    elif action == "ip":
        result = run_command("tailscale ip")
    elif action in ("up", "down"):
        reverse = "down" if action == "up" else "up"
        result = run_audited(
            f"tailscale {action}",
            tool="manage_tailscale",
            args={"action": action},
            rollback=f"tailscale {reverse}",
        )
    else:
        result = run_command(f"tailscale {action}")

    if result.returncode == 0:
        return result.stdout
    return (
        f"Error: {result.stderr}\n\n"
        "Tip: if Tailscale is not enabled, run ujust_run('enable-tailscale') first."
    )
