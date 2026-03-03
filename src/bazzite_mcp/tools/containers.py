from bazzite_mcp.runner import run_command


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

    result = run_command(f"distrobox create --name {name} --image {image} --yes")
    if result.returncode != 0:
        return f"Failed to create distrobox '{name}': {result.stderr}"
    return f"Container '{name}' created with image '{image}'.\nEnter with: distrobox enter {name}"


def manage_distrobox(name: str, action: str) -> str:
    """Manage a distrobox container."""
    if action == "enter":
        return (
            "To enter interactively, run in your terminal:\n"
            f"  distrobox enter {name}\n\n"
            "(MCP tools cannot start interactive shells)"
        )
    if action == "stop":
        result = run_command(f"distrobox stop --yes {name}")
    elif action == "remove":
        result = run_command(f"distrobox rm --force {name}")
    else:
        return f"Unknown action '{action}'. Supported: enter, stop, remove."

    return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"


def list_distroboxes() -> str:
    """List existing distrobox containers with status."""
    result = run_command("distrobox list")
    return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"


def exec_in_distrobox(name: str, command: str) -> str:
    """Run a command inside a specific distrobox container."""
    result = run_command(f"distrobox enter {name} -- {command}")
    output = result.stdout
    if result.stderr:
        output += f"\nSTDERR: {result.stderr}"
    return output


def export_distrobox_app(name: str, app: str) -> str:
    """Export a GUI app from distrobox to host menu."""
    result = run_command(f"distrobox enter {name} -- distrobox-export --app {app}")
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
        result = run_command(f"systemctl --user status {name} --no-pager")
        return result.stdout

    if action in ("start", "stop") and name:
        result = run_command(f"systemctl --user {action} {name}")
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
    result = run_command(f"podman {action} {args}")
    return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"


def manage_waydroid(action: str) -> str:
    """Manage Waydroid for running Android apps."""
    if action == "setup":
        return "Run: ujust setup-waydroid\n\nThis sets up Waydroid with Google Play support."

    if action in ("status", "start", "stop"):
        if action == "start":
            result = run_command("waydroid session start")
        elif action == "stop":
            result = run_command("waydroid session stop")
        else:
            result = run_command("waydroid status")
        return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"

    return f"Unknown action '{action}'. Supported: setup, status, start, stop."
