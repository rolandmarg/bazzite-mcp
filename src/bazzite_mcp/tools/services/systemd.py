from __future__ import annotations

from typing import Literal

from bazzite_mcp.runner import ToolError, run_audited, run_command


def _service_status(name: str, user: bool = False) -> str:
    """Get status of a systemd service."""
    command = ["systemctl"]
    if user:
        command.append("--user")
    command.extend(["status", name, "--no-pager"])
    result = run_command(command)
    return result.stdout if result.stdout else result.stderr


def _list_services(
    state: str | None = None,
    user: bool = False,
) -> str:
    """List systemd services, optionally filtered by state."""
    command = ["systemctl"]
    if user:
        command.append("--user")
    if state in ("running", "failed"):
        command.extend(["list-units", "--type=service", f"--state={state}", "--no-pager"])
    elif state in ("enabled", "disabled"):
        command.extend(["list-unit-files", "--type=service", f"--state={state}", "--no-pager"])
    else:
        command.extend(["list-units", "--type=service", "--no-pager"])
    result = run_command(command)
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

    reverse = {
        "start": "stop",
        "stop": "start",
        "enable": "disable",
        "disable": "enable",
        "enable_now": "disable_now",
        "disable_now": "enable_now",
    }.get(action)
    command = ["systemctl"]
    if user:
        command.append("--user")
    if action.endswith("_now"):
        command.extend([action.replace("_now", ""), "--now"])
    else:
        command.append(action)
    command.append(name)

    rollback_cmd: list[str] | None = None
    if reverse:
        rollback_cmd = ["systemctl"]
        if user:
            rollback_cmd.append("--user")
        if reverse.endswith("_now"):
            rollback_cmd.extend([reverse.replace("_now", ""), "--now"])
        else:
            rollback_cmd.append(reverse)
        rollback_cmd.append(name)
    result = run_audited(
        command,
        tool="manage_service",
        args={"name": name, "action": action, "user": user},
        rollback=rollback_cmd,
    )
    if result.returncode != 0:
        raise ToolError(f"Failed to {action} {name}: {result.stderr}")
    return f"Service '{name}' {action} successful."
