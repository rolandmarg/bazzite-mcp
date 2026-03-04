import shlex

from bazzite_mcp.runner import run_audited, run_command


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
        return f"Failed to create distrobox '{name}': {result.stderr}"
    return f"Container '{name}' created with image '{image}'.\nEnter with: distrobox enter {name}"


def manage_distrobox(name: str, action: str) -> str:
    """Manage a distrobox container."""
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
        return f"Unknown action '{action}'. Supported: enter, stop, remove."

    return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"


def list_distroboxes() -> str:
    """List existing distrobox containers with status."""
    result = run_command("distrobox list")
    return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"


def exec_in_distrobox(name: str, command: str) -> str:
    """Run a command inside a specific distrobox container."""
    result = run_command(f"distrobox enter {shlex.quote(name)} -- {command}")
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
        return f"Failed to export '{app}' from '{name}': {result.stderr}"
    return f"Exported '{app}' from container '{name}' to host application menu."


def manage_quadlet(
    action: str,
    name: str | None = None,
    image: str | None = None,
) -> str:
    """Manage Quadlet units for persistent containerized services."""
    if action == "list":
        result = run_command(
            "systemctl --user list-units --type=service 'podman-*' --no-pager 2>/dev/null"
        )
        return result.stdout if result.stdout.strip() else "No Quadlet services found."

    if action == "status" and name:
        result = run_command(f"systemctl --user status {shlex.quote(name)} --no-pager")
        return result.stdout

    if action in ("start", "stop") and name:
        result = run_command(f"systemctl --user {action} {shlex.quote(name)}")
        return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"

    if action == "create" and name and image:
        quadlet_dir = "~/.config/containers/systemd"
        run_command(f"mkdir -p {quadlet_dir}")
        unit_content = f"""[Container]
Image={image}
PublishPort=

[Service]
Restart=always

[Install]
WantedBy=default.target
"""
        return (
            f"To create a Quadlet service, write this to {quadlet_dir}/{name}.container:\n\n"
            f"{unit_content}\nThen run: systemctl --user daemon-reload && systemctl --user start {name}"
        )

    return "Usage: action='list|create|start|stop|status|remove', name=<service>, image=<image>"


def manage_podman(action: str, args: str = "") -> str:
    """Run podman container operations."""
    valid_actions = ("run", "stop", "rm", "pull", "ps", "images", "logs", "inspect", "exec")
    if action not in valid_actions:
        return f"Unknown action '{action}'. Supported: {', '.join(valid_actions)}"
    if action in ("run", "stop", "rm", "pull"):
        result = run_audited(
            f"podman {action} {args}",
            tool="manage_podman",
            args={"action": action, "args": args},
        )
    else:
        result = run_command(f"podman {action} {args}")
    return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"


def manage_waydroid(action: str) -> str:
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
        return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"

    return f"Unknown action '{action}'. Supported: setup, status, start, stop."
