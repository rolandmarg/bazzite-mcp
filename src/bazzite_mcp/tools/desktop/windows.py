from __future__ import annotations

import json
import re
from typing import Literal

from bazzite_mcp.desktop_env import format_graphical_error
from mcp.server.fastmcp.exceptions import ToolError

from bazzite_mcp.runner import run_command
from .accessibility import _atspi_call


def _kwin_get_windows() -> list[dict]:
    """List windows via KWin WindowsRunner DBus interface."""
    result = run_command(
        "gdbus call --session --dest org.kde.KWin "
        "--object-path /WindowsRunner "
        '--method org.kde.krunner1.Match " "'
    )
    if result.returncode != 0:
        raise ToolError(format_graphical_error("Failed to query KWin windows", result.stderr))

    raw = result.stdout
    entries = re.findall(
        r"'0_\{([^}]+)\}',\s*'([^']*)',\s*'([^']*)',\s*\d+",
        raw,
    )

    seen: set[str] = set()
    windows: list[dict] = []
    for uuid, title, wclass in entries:
        if uuid in seen:
            continue
        seen.add(uuid)
        info = _kwin_get_window_info(uuid)
        windows.append(
            {
                "id": uuid,
                "title": title,
                "class": wclass or info.get("resourceClass", ""),
                "x": info.get("x"),
                "y": info.get("y"),
                "width": info.get("width"),
                "height": info.get("height"),
                "minimized": info.get("minimized", False),
                "fullscreen": info.get("fullscreen", False),
                "desktop_file": info.get("desktopFile", ""),
            }
        )
    return windows


def _parse_window_info(raw: str) -> dict:
    info: dict = {}
    for line in raw.splitlines():
        if ": " in line:
            key, _, value = line.partition(": ")
            key = key.strip()
            value = value.strip()
            if value == "true":
                info[key] = True
            elif value == "false":
                info[key] = False
            elif value.lstrip("-").isdigit():
                info[key] = int(value)
            else:
                info[key] = value
    return info


def _kwin_get_window_info(uuid: str) -> dict:
    """Get detailed window info from KWin by UUID."""
    result = run_command(
        f"qdbus org.kde.KWin /KWin org.kde.KWin.getWindowInfo '{{{uuid}}}'"
    )
    if result.returncode != 0:
        return {}
    return _parse_window_info(result.stdout)


def _kwin_query_window_info() -> dict:
    """Get detailed info for the active window from KWin."""
    result = run_command("qdbus org.kde.KWin /KWin org.kde.KWin.queryWindowInfo")
    if result.returncode != 0:
        return {}
    return _parse_window_info(result.stdout)


def _kwin_activate(uuid: str) -> None:
    """Activate a window by UUID via KWin WindowsRunner."""
    result = run_command(
        f"qdbus org.kde.KWin /WindowsRunner org.kde.krunner1.Run '0_{{{uuid}}}' ''"
    )
    if result.returncode != 0:
        raise ToolError(format_graphical_error(f"Failed to activate window {uuid}", result.stderr))


def _resolve_window(window: str) -> str:
    """Resolve a window identifier (UUID, title substring, or class) to a UUID."""
    uuid_re = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
    )
    if uuid_re.match(window):
        return window

    windows = _kwin_get_windows()
    query = window.lower()

    for info in windows:
        if info["class"].lower() == query:
            return info["id"]
    for info in windows:
        if query in info["title"].lower():
            return info["id"]
    for info in windows:
        if query in info["class"].lower():
            return info["id"]

    available = ", ".join(f"{info['title']!r} ({info['class']})" for info in windows)
    raise ToolError(f"No window matching '{window}'. Available: {available}")


def _list_windows() -> str:
    """List all open windows with their ID, title, class, geometry, and state."""
    windows = _kwin_get_windows()
    if not windows:
        return "No windows found."
    return json.dumps(windows, indent=2)


def _activate_window(window: str) -> str:
    """Bring a window to focus and raise it to the front."""
    uuid = _resolve_window(window)
    _kwin_activate(uuid)
    info = _kwin_get_window_info(uuid)
    return f"Activated: {info.get('caption', window)}"


def _inspect_window(window: str, depth: int = 6) -> str:
    """Get the structured widget tree of a window via AT-SPI accessibility API."""
    result = _atspi_call({"op": "inspect", "query": window, "depth": depth})
    return json.dumps(result, indent=2)


def manage_windows(
    action: Literal["list", "activate", "inspect"],
    window: str | None = None,
    depth: int = 6,
) -> str:
    """List, activate, or inspect windows via KWin/AT-SPI."""
    if action == "list":
        return _list_windows()
    if not window:
        raise ToolError(f"'window' is required for action='{action}'.")
    if action == "activate":
        return _activate_window(window)
    if action == "inspect":
        return _inspect_window(window, depth)
    raise ToolError(f"Unknown action '{action}'.")
