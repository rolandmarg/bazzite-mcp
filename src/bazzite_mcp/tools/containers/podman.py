from __future__ import annotations

import shlex
from typing import Literal

from bazzite_mcp.runner import ToolError, run_audited, run_command

_BLOCKED_FLAGS = ("--privileged", "--pid=host", "--net=host", "-v /:/")


def manage_podman(
    action: Literal[
        "run", "stop", "rm", "pull", "ps", "images", "logs", "inspect", "exec"
    ],
    container: str = "",
    image: str = "",
    command: str = "",
) -> str:
    """Run podman container operations with dangerous flag blocking."""
    argv: list[str] = ["podman", action]

    if action in ("run", "pull"):
        if not image:
            raise ToolError("Error: 'image' is required for podman run.")
        for flag in _BLOCKED_FLAGS:
            if flag in image:
                raise ToolError(f"Blocked: '{flag}' is not allowed for safety.")
        argv.append(image)
    elif action in ("stop", "rm", "logs", "inspect"):
        if not container:
            raise ToolError(f"Error: 'container' is required for podman {action}.")
        argv.append(container)
    elif action == "exec":
        if not container:
            raise ToolError("Error: 'container' is required for podman exec.")
        if not command:
            raise ToolError("Error: 'command' is required for podman exec.")
        argv.append(container)
        try:
            exec_parts = shlex.split(command)
        except ValueError:
            raise ToolError("Invalid podman exec command syntax.")
        if not exec_parts:
            raise ToolError("Error: 'command' is required for podman exec.")
        argv.extend(exec_parts)
    elif action in ("ps", "images"):
        pass

    if action in ("run", "stop", "rm", "pull"):
        result = run_audited(
            argv,
            tool="manage_podman",
            args={"action": action, "container": container, "image": image},
        )
    else:
        result = run_command(argv)
    if result.returncode != 0:
        raise ToolError(f"Error: {result.stderr}")
    return result.stdout
