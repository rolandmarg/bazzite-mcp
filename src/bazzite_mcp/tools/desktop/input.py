from __future__ import annotations

import json
import shutil
import subprocess
import time
from typing import Literal

from mcp.server.fastmcp.exceptions import ToolError

from bazzite_mcp.desktop_env import build_command_env
from bazzite_mcp.screen_geometry import get_monitor_info
from .shared import SCREENSHOT_DIR, YDOTOOL_SOCKET
from .windows import _kwin_activate, _resolve_window


def _ensure_ydotoold() -> str:
    """Ensure ydotoold daemon is running. Returns socket path."""
    if not shutil.which("ydotoold"):
        raise ToolError(
            "ydotoold is not installed. Install ydotool for input simulation."
        )

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    sock = str(YDOTOOL_SOCKET)

    if YDOTOOL_SOCKET.exists():
        try:
            import socket as sock_mod

            client = sock_mod.socket(sock_mod.AF_UNIX, sock_mod.SOCK_STREAM)
            client.settimeout(1)
            client.connect(sock)
            client.close()
            return sock
        except (ConnectionRefusedError, OSError):
            YDOTOOL_SOCKET.unlink(missing_ok=True)

    subprocess.Popen(
        ["ydotoold", "--socket-path", sock],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    for _ in range(20):
        if YDOTOOL_SOCKET.exists():
            return sock
        time.sleep(0.1)

    raise ToolError("ydotoold failed to start within 2 seconds")


def _run_ydotool(argv: list[str], sock: str) -> subprocess.CompletedProcess:
    """Run a ydotool command with the socket env set (shell=False)."""
    env = build_command_env()
    env["YDOTOOL_SOCKET"] = sock
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=10,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        env=env,
    )


def _focus_window(window: str | None) -> None:
    """Activate a window by name if specified."""
    if window:
        uuid = _resolve_window(window)
        _kwin_activate(uuid)
        time.sleep(0.3)


def _get_virtual_desktop_size() -> tuple[int, int]:
    """Get the logical virtual desktop size from monitor geometry."""
    monitors = get_monitor_info()
    if not monitors:
        return (2560, 1440)
    width = max(m["x"] + m["w"] for m in monitors.values())
    height = max(m["y"] + m["h"] for m in monitors.values())
    return (width, height)


def _send_keys(keys: str, window: str | None = None) -> str:
    """Type text using ydotool."""
    sock = _ensure_ydotoold()
    _focus_window(window)

    result = _run_ydotool(
        ["ydotool", "type", "--key-delay", "12", "--", keys], sock
    )
    if result.returncode != 0:
        raise ToolError(f"ydotool type failed: {result.stderr}")

    target = f" to '{window}'" if window else ""
    return f"Typed {len(keys)} characters{target}"


def _send_key(key: str, window: str | None = None) -> str:
    """Send a key press/release using ydotool key codes."""
    sock = _ensure_ydotoold()
    _focus_window(window)

    result = _run_ydotool(["ydotool", "key", key], sock)
    if result.returncode != 0:
        raise ToolError(f"ydotool key failed: {result.stderr}")

    target = f" to '{window}'" if window else ""
    return f"Sent key {key}{target}"


def _send_mouse(
    action: str,
    x: int,
    y: int,
    button: str = "left",
    window: str | None = None,
    screenshot_meta: dict | None = None,
) -> str:
    """Send mouse input via ydotool with coordinate scaling.

    If screenshot_meta is provided (from a prior screenshot() call),
    pixel coordinates are translated to absolute desktop coordinates
    using the monitor origin and scale factor.
    """
    sock = _ensure_ydotoold()
    _focus_window(window)

    if screenshot_meta:
        abs_x = screenshot_meta.get("origin_x", 0) + x / screenshot_meta.get(
            "scale", 1.0
        )
        abs_y = screenshot_meta.get("origin_y", 0) + y / screenshot_meta.get(
            "scale", 1.0
        )
    else:
        abs_x, abs_y = float(x), float(y)

    vw, vh = _get_virtual_desktop_size()
    yd_x = int(abs_x / vw * 32767)
    yd_y = int(abs_y / vh * 32767)

    _run_ydotool(
        ["ydotool", "mousemove", "--absolute", "-x", str(yd_x), "-y", str(yd_y)],
        sock,
    )
    time.sleep(0.05)

    if action == "move":
        return f"Moved mouse to ({x}, {y})"

    button_map = {"left": "0xC0", "right": "0xC1", "middle": "0xC2"}
    btn_code = button_map.get(button, "0xC0")

    if action == "doubleclick":
        argv = ["ydotool", "click", "--repeat", "2", "--next-delay", "80", btn_code]
    elif action == "rightclick":
        argv = ["ydotool", "click", "0xC1"]
    else:
        argv = ["ydotool", "click", btn_code]

    result = _run_ydotool(argv, sock)
    if result.returncode != 0:
        raise ToolError(f"Mouse {action} failed: {result.stderr}")

    target = f" on '{window}'" if window else ""
    return f"Mouse {action} at ({x}, {y}){target}"


def send_input(
    mode: Literal["type", "key", "mouse"],
    keys: str | None = None,
    key: str | None = None,
    action: str | None = None,
    x: int | None = None,
    y: int | None = None,
    button: str = "left",
    window: str | None = None,
    screenshot_meta: str | None = None,
) -> str:
    """Send keyboard or mouse input via ydotool.

    For mouse mode with coordinates from a screenshot, pass the metadata
    JSON string from the screenshot response as screenshot_meta.
    """
    if mode == "type":
        if not keys:
            raise ToolError("'keys' is required for mode='type'.")
        return _send_keys(keys, window)
    if mode == "key":
        if not key:
            raise ToolError("'key' is required for mode='key'.")
        return _send_key(key, window)
    if mode == "mouse":
        if x is None or y is None:
            raise ToolError("'x' and 'y' are required for mode='mouse'.")
        meta = json.loads(screenshot_meta) if screenshot_meta else None
        return _send_mouse(action or "click", x, y, button, window, meta)
    raise ToolError(f"Unknown mode '{mode}'.")
