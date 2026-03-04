from __future__ import annotations

import shlex
from pathlib import Path
from typing import Literal

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


def create_distrobox(name: str, image: str | None = None) -> str:
    """Create a new distrobox container."""
    if image and image in DISTROBOX_IMAGES:
        image = DISTROBOX_IMAGES[image]
    elif not image:
        image = "ubuntu:latest"

    sname = shlex.quote(name)
    simage = shlex.quote(image)
    result = run_audited(
        f"distrobox create --name {sname} --image {simage} --yes",
        tool="create_distrobox",
        args={"name": name, "image": image},
        rollback=f"distrobox rm --force {sname}",
    )
    if result.returncode != 0:
        raise ToolError(f"Failed to create distrobox '{name}': {result.stderr}")
    return f"Container '{name}' created with image '{image}'.\nEnter with: distrobox enter {name}"


def manage_distrobox(name: str, action: Literal["enter", "stop", "remove"]) -> str:
    """Manage a distrobox container (enter, stop, or remove)."""
    sname = shlex.quote(name)
    if action == "enter":
        return (
            "To enter interactively, run in your terminal:\n"
            f"  distrobox enter {name}\n\n"
            "(MCP tools cannot start interactive shells)"
        )
    if action == "stop":
        result = run_audited(
            f"distrobox stop --yes {sname}",
            tool="manage_distrobox",
            args={"name": name, "action": action},
        )
    elif action == "remove":
        result = run_audited(
            f"distrobox rm --force {sname}",
            tool="manage_distrobox",
            args={"name": name, "action": action},
        )
    else:
        raise ToolError(f"Unknown action '{action}'. Supported: enter, stop, remove.")

    if result.returncode != 0:
        raise ToolError(f"Error: {result.stderr}")
    return result.stdout


def list_distroboxes() -> str:
    """List existing distrobox containers with status."""
    result = run_command("distrobox list")
    if result.returncode != 0:
        raise ToolError(f"Error: {result.stderr}")
    return result.stdout


def exec_in_distrobox(name: str, command: str) -> str:
    """Run a command inside a specific distrobox container.

    Use this to install packages, run builds, or execute tools inside a distrobox.
    The command runs inside the container, not on the host.
    """
    try:
        parts = shlex.split(command)
    except ValueError:
        raise ToolError("Invalid command syntax.")
    safe_cmd = shlex.join(parts)
    result = run_audited(
        f"distrobox enter {shlex.quote(name)} -- {safe_cmd}",
        tool="exec_in_distrobox",
        args={"name": name, "command": command},
    )
    output = result.stdout
    if result.stderr:
        output += f"\nSTDERR: {result.stderr}"
    return output


def export_distrobox_app(name: str, app: str) -> str:
    """Export a GUI app from distrobox to host menu."""
    result = run_audited(
        f"distrobox enter {shlex.quote(name)} -- distrobox-export --app {shlex.quote(app)}",
        tool="export_distrobox_app",
        args={"name": name, "app": app},
    )
    if result.returncode != 0:
        raise ToolError(f"Failed to export '{app}' from '{name}': {result.stderr}")
    return f"Exported '{app}' from container '{name}' to host application menu."


def manage_quadlet(
    action: Literal["list", "create", "start", "stop", "status", "remove"],
    name: str | None = None,
    image: str | None = None,
) -> str:
    """Manage Quadlet units for persistent containerized services.

    Quadlet combines systemd + podman for declarative container services.
    Use 'list' to see existing services, 'create' to make a new one.
    """
    if action == "list":
        result = run_command(
            "systemctl --user list-units --type=service 'podman-*' --no-pager 2>/dev/null"
        )
        return result.stdout if result.stdout.strip() else "No Quadlet services found."

    def service_name(unit: str) -> str:
        return unit if unit.endswith(".service") else f"{unit}.service"

    def unit_base(unit: str) -> str:
        return unit[:-8] if unit.endswith(".service") else unit

    if action == "status" and name:
        result = run_command(
            f"systemctl --user status {shlex.quote(service_name(name))} --no-pager"
        )
        return result.stdout

    if action in ("start", "stop") and name:
        result = run_audited(
            f"systemctl --user {action} {shlex.quote(service_name(name))}",
            tool="manage_quadlet",
            args={"action": action, "name": name},
        )
        if result.returncode != 0:
            raise ToolError(f"Error: {result.stderr}")
        return result.stdout

    if action == "create" and name and image:
        base_name = unit_base(name)
        quadlet_dir = Path.home() / ".config" / "containers" / "systemd"
        quadlet_dir.mkdir(parents=True, exist_ok=True)
        unit_path = quadlet_dir / f"{base_name}.container"
        unit_content = f"""[Container]
Image={image}
PublishPort=

[Service]
Restart=always

[Install]
WantedBy=default.target
"""
        unit_path.write_text(unit_content, encoding="utf-8")

        reload_result = run_audited(
            "systemctl --user daemon-reload",
            tool="manage_quadlet",
            args={"action": "create", "name": name, "image": image},
            rollback=f"rm -f {shlex.quote(str(unit_path))}",
        )
        if reload_result.returncode != 0:
            raise ToolError(
                f"Quadlet file created but daemon-reload failed: {reload_result.stderr}"
            )

        return (
            f"Created Quadlet unit: {unit_path}\n"
            f"Start it with: systemctl --user start {service_name(name)}"
        )

    if action == "remove" and name:
        svc = service_name(name)
        unit_path = (
            Path.home()
            / ".config"
            / "containers"
            / "systemd"
            / f"{unit_base(name)}.container"
        )

        stop_result = run_audited(
            f"systemctl --user stop {shlex.quote(svc)}",
            tool="manage_quadlet",
            args={"action": "remove-stop", "name": name},
        )

        disable_result = run_audited(
            f"systemctl --user disable {shlex.quote(svc)}",
            tool="manage_quadlet",
            args={"action": "remove-disable", "name": name},
        )

        removed_file = False
        if unit_path.exists():
            unit_path.unlink()
            removed_file = True

        reload_result = run_audited(
            "systemctl --user daemon-reload",
            tool="manage_quadlet",
            args={"action": "remove", "name": name},
        )

        if reload_result.returncode != 0:
            raise ToolError(
                f"Removed file but daemon-reload failed: {reload_result.stderr}"
            )

        notes: list[str] = []
        if stop_result.returncode != 0:
            notes.append(f"stop: {stop_result.stderr or stop_result.stdout}")
        if disable_result.returncode != 0:
            notes.append(f"disable: {disable_result.stderr or disable_result.stdout}")
        if not removed_file:
            notes.append(f"unit file not found: {unit_path}")

        if notes:
            return f"Processed Quadlet removal for {svc}.\n" + "\n".join(notes)
        return f"Removed Quadlet unit {svc} and reloaded systemd user daemon."

    raise ToolError(
        "Usage: action='list|create|start|stop|status|remove', name=<service>, image=<image>"
    )


def manage_podman(
    action: Literal[
        "run", "stop", "rm", "pull", "ps", "images", "logs", "inspect", "exec"
    ],
    container: str = "",
    image: str = "",
    command: str = "",
) -> str:
    """Run podman container operations.

    Use 'ps' to list running containers, 'images' to list images.
    Use 'run' with an image, 'stop'/'rm' with a container name/ID.
    Use 'logs'/'inspect' with a container name/ID.
    """
    BLOCKED_FLAGS = ("--privileged", "--pid=host", "--net=host", "-v /:/")
    parts: list[str] = ["podman", action]

    if action in ("run", "pull") and image:
        # Block dangerous flags
        for flag in BLOCKED_FLAGS:
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
        parts.extend(shlex.quote(p) for p in exec_parts)
    elif action in ("ps", "images"):
        pass  # No extra args needed
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


def manage_waydroid(action: Literal["setup", "status", "start", "stop"]) -> str:
    """Manage Waydroid for running Android apps."""
    if action == "setup":
        return "Run: ujust setup-waydroid\n\nThis sets up Waydroid with Google Play support."

    if action in ("status", "start", "stop"):
        if action == "start":
            result = run_audited(
                "waydroid session start",
                tool="manage_waydroid",
                args={"action": action},
                rollback="waydroid session stop",
            )
        elif action == "stop":
            result = run_audited(
                "waydroid session stop",
                tool="manage_waydroid",
                args={"action": action},
            )
        else:
            result = run_command("waydroid status")
        if result.returncode != 0:
            raise ToolError(f"Error: {result.stderr}")
        return result.stdout

    raise ToolError(
        f"Unknown action '{action}'. Supported: setup, status, start, stop."
    )
