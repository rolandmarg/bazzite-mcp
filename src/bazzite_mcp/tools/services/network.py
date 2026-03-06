from __future__ import annotations

import shlex
from typing import Literal

from bazzite_mcp.runner import ToolError, run_audited, run_command


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
        result = run_command(["nmcli", "connection", "show"])
    elif action in ("up", "down", "delete") and name:
        result = run_audited(
            ["nmcli", "connection", action, name],
            tool="manage_network",
            args={"action": action, "name": name},
        )
    elif action == "modify" and name and properties:
        try:
            prop_parts = shlex.split(properties)
        except ValueError:
            raise ToolError("Invalid properties syntax.")
        result = run_audited(
            ["nmcli", "connection", "modify", name, *prop_parts],
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


def manage_network(
    action: Literal["status", "show", "up", "down", "delete", "modify"],
    name: str | None = None,
    properties: str | None = None,
) -> str:
    """Manage NetworkManager connections and view network status."""
    if action == "status":
        return _network_status()
    return _manage_connection(action, name, properties)
