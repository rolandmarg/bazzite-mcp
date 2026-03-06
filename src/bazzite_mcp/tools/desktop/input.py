from __future__ import annotations

import shutil
import subprocess
import time
from typing import Literal

from mcp.server.fastmcp.exceptions import ToolError

from bazzite_mcp.runner import run_command
from . import capture as capture_mod
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


def _shell_quote(text: str) -> str:
    return "'" + text.replace("'", "'\\''") + "'"


def _get_virtual_desktop_size() -> tuple[int, int]:
    """Get the logical virtual desktop size from monitor geometry."""
    from bazzite_mcp.kwin_screenshot import get_monitor_info

    monitors = get_monitor_info()
    if not monitors:
        return (2560, 1440)
    width = max(monitor["x"] + monitor["w"] for monitor in monitors.values())
    height = max(monitor["y"] + monitor["h"] for monitor in monitors.values())
    return (width, height)


def _send_keys(keys: str, window: str | None = None) -> str:
    """Send keyboard input using ydotool (Wayland-native)."""
    sock = _ensure_ydotoold()

    if window:
        uuid = _resolve_window(window)
        _kwin_activate(uuid)
        time.sleep(0.3)

    result = run_command(
        f"YDOTOOL_SOCKET={sock} ydotool type --key-delay 12 -- {_shell_quote(keys)}"
    )
    if result.returncode != 0:
        raise ToolError(f"ydotool type failed: {result.stderr}")

    target = f" to '{window}'" if window else ""
    return f"Typed {len(keys)} characters{target}"


def _send_key(key: str, window: str | None = None) -> str:
    """Send a key press/release using ydotool key codes."""
    sock = _ensure_ydotoold()

    if window:
        uuid = _resolve_window(window)
        _kwin_activate(uuid)
        time.sleep(0.3)

    result = run_command(f"YDOTOOL_SOCKET={sock} ydotool key {_shell_quote(key)}")
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
) -> str:
    """Send mouse input via ydotool with coordinate scaling."""
    sock = _ensure_ydotoold()

    if window:
        uuid = _resolve_window(window)
        _kwin_activate(uuid)
        time.sleep(0.3)

    if capture_mod._last_screenshot_meta:
        meta = capture_mod._last_screenshot_meta
        abs_x = meta["origin_x"] + x / meta["scale"]
        abs_y = meta["origin_y"] + y / meta["scale"]
    else:
        abs_x, abs_y = float(x), float(y)

    vw, vh = _get_virtual_desktop_size()
    yd_x = int(abs_x / vw * 32767)
    yd_y = int(abs_y / vh * 32767)

    env = f"YDOTOOL_SOCKET={sock}"
    run_command(f"{env} ydotool mousemove --absolute -x {yd_x} -y {yd_y}")
    time.sleep(0.05)

    if action == "move":
        return f"Moved mouse to ({x}, {y})"

    button_map = {"left": "0xC0", "right": "0xC1", "middle": "0xC2"}
    btn_code = button_map.get(button, "0xC0")

    if action == "doubleclick":
        click_cmd = f"{env} ydotool click --repeat 2 --next-delay 80 {btn_code}"
    elif action == "rightclick":
        click_cmd = f"{env} ydotool click 0xC1"
    else:
        click_cmd = f"{env} ydotool click {btn_code}"

    result = run_command(click_cmd)
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
) -> str:
    """Send keyboard or mouse input via ydotool."""
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
        return _send_mouse(action or "click", x, y, button, window)
    raise ToolError(f"Unknown mode '{mode}'.")
