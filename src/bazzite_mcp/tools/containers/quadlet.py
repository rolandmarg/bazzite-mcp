from __future__ import annotations

import shlex
from pathlib import Path
from typing import Literal

from bazzite_mcp.runner import ToolError, run_audited, run_command


def manage_quadlet(
    action: Literal["list", "create", "start", "stop", "status", "remove"],
    name: str | None = None,
    image: str | None = None,
) -> str:
    """Manage Quadlet units for persistent containerized services."""
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
