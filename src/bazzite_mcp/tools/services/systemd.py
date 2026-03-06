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


def manage_service(
    name: str | None = None,
    action: Literal[
        "start", "stop", "restart", "enable", "disable",
        "enable_now", "disable_now", "status", "list"
    ] = "status",
    user: bool = False,
    state: Literal["running", "failed", "enabled", "disabled"] | None = None,
) -> str:
    """Manage systemd services: start, stop, restart, enable, disable, status, or list."""
    if action == "status":
        if not name:
            raise ToolError("'name' is required for action='status'.")
        return _service_status(name, user)
    if action == "list":
        return _list_services(state, user)

    if not name:
        raise ToolError(f"'name' is required for action='{action}'.")

    scope = "--user" if user else ""
    sname = shlex.quote(name)
    reverse = {
        "start": "stop",
        "stop": "start",
        "enable": "disable",
        "disable": "enable",
        "enable_now": "disable_now",
        "disable_now": "enable_now",
    }.get(action)
    command_action = action.replace("_now", " --now")
    rollback_cmd = f"systemctl {scope} {reverse} {sname}" if reverse else None
    if rollback_cmd:
        rollback_cmd = rollback_cmd.replace("_now", " --now")
    result = run_audited(
        f"systemctl {scope} {command_action} {sname}",
        tool="manage_service",
        args={"name": name, "action": action, "user": user},
        rollback=rollback_cmd,
    )
    if result.returncode != 0:
        raise ToolError(f"Failed to {action} {name}: {result.stderr}")
    return f"Service '{name}' {action} successful."
