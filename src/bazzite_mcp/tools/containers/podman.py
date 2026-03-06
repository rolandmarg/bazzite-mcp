from __future__ import annotations

import shlex
from typing import Literal

from bazzite_mcp.runner import ToolError, run_audited, run_command


def manage_podman(
    action: Literal[
        "run", "stop", "rm", "pull", "ps", "images", "logs", "inspect", "exec"
    ],
    container: str = "",
    image: str = "",
    command: str = "",
) -> str:
    """Run podman container operations with dangerous flag blocking."""
    blocked_flags = ("--privileged", "--pid=host", "--net=host", "-v /:/")
    parts: list[str] = ["podman", action]

    if action in ("run", "pull") and image:
        for flag in blocked_flags:
            if flag in image:
                raise ToolError(f"Blocked: '{flag}' is not allowed for safety.")
        parts.append(shlex.quote(image))
    elif action in ("stop", "rm", "logs", "inspect") and container:
        parts.append(shlex.quote(container))
    elif action == "exec" and container and command:
        parts.append(shlex.quote(container))
        try:
            exec_parts = shlex.split(command)
        except ValueError:
            raise ToolError("Invalid podman exec command syntax.")
        if not exec_parts:
            raise ToolError("Error: 'command' is required for podman exec.")
        parts.extend(shlex.quote(part) for part in exec_parts)
    elif action in ("ps", "images"):
        pass
    elif action == "run" and not image:
        raise ToolError("Error: 'image' is required for podman run.")
    elif action == "exec" and not command:
        raise ToolError("Error: 'command' is required for podman exec.")
    elif action == "exec" and not container:
        raise ToolError("Error: 'container' is required for podman exec.")

    cmd = " ".join(parts)
    if action in ("run", "stop", "rm", "pull"):
        result = run_audited(
            cmd,
            tool="manage_podman",
            args={"action": action, "container": container, "image": image},
        )
    else:
        result = run_command(cmd)
    if result.returncode != 0:
        raise ToolError(f"Error: {result.stderr}")
    return result.stdout
