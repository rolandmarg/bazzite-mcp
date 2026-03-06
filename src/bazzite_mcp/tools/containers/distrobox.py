from __future__ import annotations

import shlex
from typing import Literal

from bazzite_mcp.guardrails import check_command
from bazzite_mcp.runner import ToolError, run_audited, run_command


DISTROBOX_IMAGES = {
    "ubuntu": "ubuntu:latest",
    "fedora": "fedora:latest",
    "arch": "archlinux:latest",
    "debian": "debian:latest",
    "opensuse": "opensuse/tumbleweed:latest",
    "alpine": "alpine:latest",
    "void": "voidlinux/voidlinux:latest",
}


def _create_distrobox(name: str, image: str | None = None) -> str:
    """Create a new distrobox container."""
    if image and image in DISTROBOX_IMAGES:
        image = DISTROBOX_IMAGES[image]
    elif not image:
        image = "ubuntu:latest"

    result = run_audited(
        ["distrobox", "create", "--name", name, "--image", image, "--yes"],
        tool="manage_distrobox",
        args={"name": name, "image": image},
        rollback=["distrobox", "rm", "--force", name],
    )
    if result.returncode != 0:
        raise ToolError(f"Failed to create distrobox '{name}': {result.stderr}")
    return f"Container '{name}' created with image '{image}'.\nEnter with: distrobox enter {name}"


def _distrobox_ctrl(name: str, action: str) -> str:
    """Manage a distrobox container (enter, stop, or remove)."""
    if action == "enter":
        return (
            "To enter interactively, run in your terminal:\n"
            f"  distrobox enter {name}\n\n"
            "(MCP tools cannot start interactive shells)"
        )
    if action == "stop":
        result = run_audited(
            ["distrobox", "stop", "--yes", name],
            tool="manage_distrobox",
            args={"name": name, "action": action},
        )
    elif action == "remove":
        result = run_audited(
            ["distrobox", "rm", "--force", name],
            tool="manage_distrobox",
            args={"name": name, "action": action},
        )
    else:
        raise ToolError(f"Unknown action '{action}'. Supported: enter, stop, remove.")

    if result.returncode != 0:
        raise ToolError(f"Error: {result.stderr}")
    return result.stdout


def _list_distroboxes() -> str:
    """List existing distrobox containers with status."""
    result = run_command(["distrobox", "list"])
    if result.returncode != 0:
        raise ToolError(f"Error: {result.stderr}")
    return result.stdout


def _exec_in_distrobox(name: str, command: str) -> str:
    """Run a command inside a specific distrobox container."""
    check = check_command(command)
    try:
        parts = shlex.split(command)
    except ValueError:
        raise ToolError("Invalid command syntax.")
    result = run_audited(
        ["distrobox", "enter", name, "--", *parts],
        tool="manage_distrobox",
        args={"name": name, "command": command},
    )
    output = result.stdout
    if check.warning and not (result.warning and check.warning in result.warning):
        output = f"WARNING: {check.warning}\n\n{output}"
    if result.stderr:
        output += f"\nSTDERR: {result.stderr}"
    return output


def _export_distrobox_app(name: str, app: str) -> str:
    """Export a GUI app from distrobox to host menu."""
    result = run_audited(
        ["distrobox", "enter", name, "--", "distrobox-export", "--app", app],
        tool="manage_distrobox",
        args={"name": name, "app": app},
    )
    if result.returncode != 0:
        raise ToolError(f"Failed to export '{app}' from '{name}': {result.stderr}")
    return f"Exported '{app}' from container '{name}' to host application menu."


def manage_distrobox(
    action: Literal["create", "list", "enter", "stop", "remove", "exec", "export"],
    name: str | None = None,
    image: str | None = None,
    command: str | None = None,
    app: str | None = None,
) -> str:
    """Manage distrobox containers: create, list, enter, stop, remove, exec, or export apps."""
    if action == "list":
        return _list_distroboxes()
    if not name:
        raise ToolError(f"'name' is required for action='{action}'.")
    if action == "create":
        return _create_distrobox(name, image)
    if action in ("enter", "stop", "remove"):
        return _distrobox_ctrl(name, action)
    if action == "exec":
        if not command:
            raise ToolError("'command' is required for action='exec'.")
        return _exec_in_distrobox(name, command)
    if action == "export":
        if not app:
            raise ToolError("'app' is required for action='export'.")
        return _export_distrobox_app(name, app)
    raise ToolError(f"Unknown action '{action}'.")
