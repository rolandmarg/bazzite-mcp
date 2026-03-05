from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from textwrap import dedent
from typing import Literal

from mcp.server.fastmcp.exceptions import ToolError
from fastmcp.utilities.types import Image

from bazzite_mcp.kwin_screenshot import capture_active_window, capture_screen
from bazzite_mcp.portal import PortalClient, get_portal
from bazzite_mcp.runner import run_command

SCREENSHOT_DIR = Path("/tmp/bazzite-mcp")
YDOTOOL_SOCKET = SCREENSHOT_DIR / "ydotool.sock"

# System Python is needed for AT-SPI (gi module lives in system site-packages).
_SYSTEM_PYTHON = "/usr/bin/python3"

# Module-level state: last screenshot coordinate metadata for send_input offset.
_last_screenshot_meta: dict | None = None


def _get_portal() -> PortalClient:
    """Get portal client (lazy, may not be connected)."""
    return get_portal()


# ---------------------------------------------------------------------------
# Internal helpers — KWin DBus
# ---------------------------------------------------------------------------


def _kwin_get_windows() -> list[dict]:
    """List windows via KWin WindowsRunner DBus interface."""
    result = run_command(
        "gdbus call --session --dest org.kde.KWin "
        "--object-path /WindowsRunner "
        '--method org.kde.krunner1.Match " "'
    )
    if result.returncode != 0:
        raise ToolError(f"Failed to query KWin windows: {result.stderr}")

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


def _kwin_get_window_info(uuid: str) -> dict:
    """Get detailed window info from KWin by UUID."""
    result = run_command(
        f"qdbus org.kde.KWin /KWin org.kde.KWin.getWindowInfo '{{{uuid}}}'"
    )
    if result.returncode != 0:
        return {}
    info: dict = {}
    for line in result.stdout.splitlines():
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


def _kwin_get_active_uuid() -> str | None:
    """Get the UUID of the currently active window."""
    result = run_command("qdbus org.kde.KWin /KWin org.kde.KWin.queryWindowInfo")
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if line.startswith("uuid:"):
            raw = line.partition(":")[2].strip()
            return raw.strip("{}")
    return None


def _kwin_activate(uuid: str) -> None:
    """Activate a window by UUID via KWin WindowsRunner."""
    result = run_command(
        f"qdbus org.kde.KWin /WindowsRunner org.kde.krunner1.Run '0_{{{uuid}}}' ''"
    )
    if result.returncode != 0:
        raise ToolError(f"Failed to activate window {uuid}: {result.stderr}")


def _resolve_window(window: str) -> str:
    """Resolve a window identifier (UUID, title substring, or class) to a UUID."""
    uuid_re = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
    )
    if uuid_re.match(window):
        return window

    windows = _kwin_get_windows()
    query = window.lower()

    for w in windows:
        if w["class"].lower() == query:
            return w["id"]
    for w in windows:
        if query in w["title"].lower():
            return w["id"]
    for w in windows:
        if query in w["class"].lower():
            return w["id"]

    available = ", ".join(f"{w['title']!r} ({w['class']})" for w in windows)
    raise ToolError(f"No window matching '{window}'. Available: {available}")


# ---------------------------------------------------------------------------
# Internal helpers — screenshots
# ---------------------------------------------------------------------------


def _require_spectacle() -> None:
    if not shutil.which("spectacle"):
        raise ToolError(
            "spectacle is not installed. "
            "It should be pre-installed on Bazzite KDE — check your image."
        )


def _capture_and_compress(spectacle_args: str, max_width: int = 2560) -> Image:
    """Run spectacle, compress to JPEG, return inline MCP Image.

    max_width caps the output width (only shrinks, never upscales).
    """
    _require_spectacle()
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = int(time.time())
    png_path = SCREENSHOT_DIR / f"capture-{timestamp}.png"

    result = run_command(
        f"spectacle {spectacle_args} --background --nonotify --output {png_path}"
    )
    if result.returncode != 0:
        raise ToolError(f"Spectacle capture failed: {result.stderr}")

    # Compress to JPEG if ImageMagick available
    if shutil.which("magick"):
        jpg_path = png_path.with_suffix(".jpg")
        # ">" flag = only shrink, never upscale
        resize_arg = f"-resize {max_width}x\\> " if max_width else ""
        conv = run_command(f"magick {png_path} {resize_arg}-quality 85 {jpg_path}")
        if conv.returncode == 0:
            png_path.unlink(missing_ok=True)
            return Image(path=str(jpg_path))

    return Image(path=str(png_path))


# ---------------------------------------------------------------------------
# Internal helpers — AT-SPI (runs via system Python subprocess)
# ---------------------------------------------------------------------------

# AT-SPI helper script executed by system Python (which has gi/PyGObject).
_ATSPI_HELPER = dedent("""\
    import gi, json, sys
    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi
    import warnings
    warnings.filterwarnings("ignore", category=DeprecationWarning)

    Atspi.init()

    STATE_NAMES = {
        Atspi.StateType.FOCUSED: "focused",
        Atspi.StateType.VISIBLE: "visible",
        Atspi.StateType.SHOWING: "showing",
        Atspi.StateType.ENABLED: "enabled",
        Atspi.StateType.CHECKED: "checked",
        Atspi.StateType.SELECTED: "selected",
        Atspi.StateType.EDITABLE: "editable",
        Atspi.StateType.ACTIVE: "active",
        Atspi.StateType.EXPANDABLE: "expandable",
        Atspi.StateType.EXPANDED: "expanded",
        Atspi.StateType.SENSITIVE: "sensitive",
    }

    def _states(node):
        ss = node.get_state_set()
        return [n for s, n in STATE_NAMES.items() if ss.contains(s)]

    def _geom(node):
        try:
            r = node.get_extents(Atspi.CoordType.SCREEN)
            if r.width > 0:
                return {"x": r.x, "y": r.y, "w": r.width, "h": r.height}
        except Exception:
            pass
        return None

    def _actions(node):
        try:
            ai = node.get_action_iface()
            if ai:
                return [ai.get_action_name(i) for i in range(ai.get_n_actions())]
        except Exception:
            pass
        return []

    def _text(node):
        try:
            ti = node.get_text_iface()
            if ti:
                n = ti.get_character_count()
                if n > 0:
                    return ti.get_text(0, min(n, 200))
        except Exception:
            pass
        return ""

    def _value(node):
        try:
            vi = node.get_value_iface()
            if vi:
                return vi.get_current_value()
        except Exception:
            pass
        return None

    def dump(node, depth=0, max_depth=6):
        if depth > max_depth or not node:
            return None
        try:
            role = node.get_role_name()
            name = node.get_name() or ""
            d = {"role": role}
            if name:
                d["name"] = name
            st = _states(node)
            if st:
                d["states"] = st
            g = _geom(node)
            if g:
                d["geom"] = g
            acts = _actions(node)
            if acts:
                d["actions"] = acts
            txt = _text(node)
            if txt:
                d["text"] = txt
            val = _value(node)
            if val is not None:
                d["value"] = val
            kids = []
            for i in range(min(node.get_child_count(), 100)):
                c = dump(node.get_child_at_index(i), depth + 1, max_depth)
                if c:
                    kids.append(c)
            if kids:
                d["children"] = kids
            return d
        except Exception as e:
            return {"error": str(e)}

    def find_app(name_query):
        desktop = Atspi.get_desktop(0)
        q = name_query.lower()
        for i in range(desktop.get_child_count()):
            app = desktop.get_child_at_index(i)
            if not app:
                continue
            app_name = (app.get_name() or "").lower()
            if q in app_name:
                return app
            # Check window titles
            for j in range(app.get_child_count()):
                win = app.get_child_at_index(j)
                if win and q in (win.get_name() or "").lower():
                    return app
        return None

    def do_action_on(app, element_query, action_name):
        \"\"\"Find an element by role+name and perform an action on it.\"\"\"
        q = element_query.lower()
        def search(node, depth=0):
            if depth > 10 or not node:
                return None
            try:
                role = node.get_role_name() or ""
                name = (node.get_name() or "").lower()
                txt = ""
                try:
                    ti = node.get_text_iface()
                    if ti and ti.get_character_count() > 0:
                        txt = ti.get_text(0, min(ti.get_character_count(), 200)).lower()
                except Exception:
                    pass
                if q in name or q in role or q in txt:
                    ai = node.get_action_iface()
                    if ai:
                        for i in range(ai.get_n_actions()):
                            if ai.get_action_name(i).lower() == action_name.lower():
                                ok = ai.do_action(i)
                                return {"found": True, "did_action": ok,
                                        "element": {"role": role, "name": node.get_name() or ""}}
                for i in range(min(node.get_child_count(), 100)):
                    result = search(node.get_child_at_index(i), depth + 1)
                    if result:
                        return result
            except Exception:
                pass
            return None

        for j in range(app.get_child_count()):
            win = app.get_child_at_index(j)
            result = search(win)
            if result:
                return result
        return None

    def set_text_on(app, element_query, new_text):
        \"\"\"Find a text element and set its content.\"\"\"
        q = element_query.lower()
        def search(node, depth=0):
            if depth > 10 or not node:
                return None
            try:
                role = node.get_role_name() or ""
                name = (node.get_name() or "").lower()
                if q in name or q in role:
                    eti = node.get_editable_text_iface()
                    if eti:
                        ti = node.get_text_iface()
                        if ti:
                            old_len = ti.get_character_count()
                            if old_len > 0:
                                eti.delete_text(0, old_len)
                            eti.insert_text(0, new_text, len(new_text))
                            return {"found": True, "set": True,
                                    "element": {"role": role, "name": node.get_name() or ""}}
                for i in range(min(node.get_child_count(), 100)):
                    result = search(node.get_child_at_index(i), depth + 1)
                    if result:
                        return result
            except Exception:
                pass
            return None

        for j in range(app.get_child_count()):
            win = app.get_child_at_index(j)
            result = search(win)
            if result:
                return result
        return None

    # --- Main dispatch ---
    cmd = json.loads(sys.argv[1])

    if cmd["op"] == "list_apps":
        desktop = Atspi.get_desktop(0)
        apps = []
        for i in range(desktop.get_child_count()):
            app = desktop.get_child_at_index(i)
            if app:
                windows = []
                for j in range(app.get_child_count()):
                    win = app.get_child_at_index(j)
                    if win:
                        windows.append(win.get_name() or "")
                apps.append({
                    "name": app.get_name() or "(unnamed)",
                    "pid": app.get_process_id(),
                    "windows": windows,
                })
        print(json.dumps(apps))

    elif cmd["op"] == "inspect":
        app = find_app(cmd["query"])
        if not app:
            print(json.dumps({"error": f"App not found: {cmd['query']}",
                              "hint": "App may not expose accessibility data. Use screenshot(target='window') for visual inspection."}))
        else:
            trees = []
            for j in range(app.get_child_count()):
                win = app.get_child_at_index(j)
                t = dump(win, max_depth=cmd.get("depth", 6))
                if t:
                    trees.append(t)
            print(json.dumps({"app": app.get_name(), "pid": app.get_process_id(),
                              "windows": trees}))

    elif cmd["op"] == "do_action":
        app = find_app(cmd["app"])
        if not app:
            print(json.dumps({"error": f"App not found: {cmd['app']}"}))
        else:
            result = do_action_on(app, cmd["element"], cmd["action"])
            if result:
                print(json.dumps(result))
            else:
                print(json.dumps({"found": False,
                    "error": f"No element matching '{cmd['element']}' with action '{cmd['action']}'"}))

    elif cmd["op"] == "set_text":
        app = find_app(cmd["app"])
        if not app:
            print(json.dumps({"error": f"App not found: {cmd['app']}"}))
        else:
            result = set_text_on(app, cmd["element"], cmd["text"])
            if result:
                print(json.dumps(result))
            else:
                print(json.dumps({"found": False,
                    "error": f"No editable element matching '{cmd['element']}'"}))
""")


def _atspi_call(cmd: dict) -> dict:
    """Call the AT-SPI helper via system Python and return parsed JSON."""
    result = subprocess.run(
        [_SYSTEM_PYTHON, "-c", _ATSPI_HELPER, json.dumps(cmd)],
        capture_output=True,
        text=True,
        timeout=10,
        stdin=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        raise ToolError(f"AT-SPI query failed: {result.stderr.strip()}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        raise ToolError(f"AT-SPI returned invalid JSON: {result.stdout[:200]}")


# ---------------------------------------------------------------------------
# Internal helpers — ydotool
# ---------------------------------------------------------------------------


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

            s = sock_mod.socket(sock_mod.AF_UNIX, sock_mod.SOCK_STREAM)
            s.settimeout(1)
            s.connect(sock)
            s.close()
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


def _shell_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


# ---------------------------------------------------------------------------
# Private tool implementations
# ---------------------------------------------------------------------------


def _screenshot_desktop() -> Image:
    """Capture the full desktop via Spectacle fullscreen."""
    return _capture_and_compress("--fullscreen")


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


def _ensure_ydotool_flat_accel(sock: str) -> None:
    """Set flat acceleration profile on ydotool devices so moves are 1:1 pixels."""
    # Find ydotool pointer devices via KWin InputDeviceManager
    result = run_command(
        "gdbus call --session --dest org.kde.KWin "
        "--object-path /org/kde/KWin/InputDevice "
        "--method org.kde.KWin.InputDeviceManager.ListPointers"
    )
    if result.returncode != 0:
        return  # best-effort, don't block on failure
    sysnames = re.findall(r"'(event\d+)'", result.stdout)
    for sysname in sysnames:
        path = f"/org/kde/KWin/InputDevice/{sysname}"
        # Check if this is a ydotool device
        name_result = run_command(
            f"gdbus call --session --dest org.kde.KWin "
            f"--object-path {path} "
            f"--method org.freedesktop.DBus.Properties.Get "
            f"org.kde.KWin.InputDevice name"
        )
        if "ydotool" not in name_result.stdout:
            continue
        # Set flat acceleration profile
        run_command(
            f"gdbus call --session --dest org.kde.KWin "
            f"--object-path {path} "
            f"--method org.freedesktop.DBus.Properties.Set "
            f"org.kde.KWin.InputDevice pointerAccelerationProfileFlat "
            f'"<boolean true>"'
        )


def _ydotool_move_absolute(sock: str, x: int, y: int) -> None:
    """Move cursor to absolute logical coordinates via two relative ydotool moves."""
    # ydotool --absolute is broken on Wayland (uses REL device, second move lost).
    # Workaround: large negative move to origin, then positive move to target.
    env = f"YDOTOOL_SOCKET={sock}"
    result = run_command(f"{env} ydotool mousemove -x -32768 -y -32768")
    if result.returncode != 0:
        raise ToolError(f"Mouse move to origin failed: {result.stderr}")
    time.sleep(0.05)
    result = run_command(f"{env} ydotool mousemove -x {x} -y {y}")
    if result.returncode != 0:
        raise ToolError(f"Mouse move to ({x}, {y}) failed: {result.stderr}")


def _send_mouse(
    action: str,
    x: int,
    y: int,
    button: str = "left",
    window: str | None = None,
) -> str:
    """Send mouse input using portal (preferred) or ydotool (fallback)."""
    portal = _get_portal()
    if portal.is_connected:
        if window:
            uuid = _resolve_window(window)
            _kwin_activate(uuid)
            time.sleep(0.3)

        # Apply coordinate offset from last screenshot metadata
        if _last_screenshot_meta:
            meta = _last_screenshot_meta
            abs_x = meta["origin_x"] + x / meta["scale"]
            abs_y = meta["origin_y"] + y / meta["scale"]
        else:
            abs_x, abs_y = float(x), float(y)
        portal.pointer_move(abs_x, abs_y)
        time.sleep(0.05)

        if action == "move":
            return f"Moved mouse to ({x}, {y})"

        evdev_btn = {"left": 272, "right": 273, "middle": 274}.get(button, 272)
        if action == "doubleclick":
            portal.click(evdev_btn)
            time.sleep(0.08)
            portal.click(evdev_btn)
        else:
            portal.click(evdev_btn, action)

        target = f" on '{window}'" if window else ""
        return f"Mouse {action} at ({x}, {y}){target}"

    # --- Fallback: ydotool (existing code below, unchanged) ---
    sock = _ensure_ydotoold()
    _ensure_ydotool_flat_accel(sock)

    if window:
        uuid = _resolve_window(window)
        _kwin_activate(uuid)
        time.sleep(0.3)

    button_map = {"left": "0xC0", "right": "0xC1", "middle": "0xC2"}
    btn_code = button_map.get(button, "0xC0")

    _ydotool_move_absolute(sock, x, y)

    if action == "move":
        return f"Moved mouse to ({x}, {y})"

    if action == "doubleclick":
        click_cmd = (
            f"YDOTOOL_SOCKET={sock} ydotool click --repeat 2 --next-delay 80 {btn_code}"
        )
    elif action == "rightclick":
        click_cmd = f"YDOTOOL_SOCKET={sock} ydotool click 0xC1"
    else:
        click_cmd = f"YDOTOOL_SOCKET={sock} ydotool click {btn_code}"

    result = run_command(click_cmd)
    if result.returncode != 0:
        raise ToolError(f"Mouse {action} failed: {result.stderr}")

    target = f" on '{window}'" if window else ""
    return f"Mouse {action} at ({x}, {y}){target}"


# ---------------------------------------------------------------------------
# Public MCP tools — Accessibility (kept as-is)
# ---------------------------------------------------------------------------


def interact(
    window: str,
    element: str,
    action: str = "Press",
) -> str:
    """Perform an action on a UI element via AT-SPI accessibility API."""
    result = _atspi_call(
        {
            "op": "do_action",
            "app": window,
            "element": element,
            "action": action,
        }
    )

    if result.get("error"):
        raise ToolError(result["error"])

    if result.get("found") and result.get("did_action"):
        el = result.get("element", {})
        return f"Performed '{action}' on {el.get('role', '?')}: \"{el.get('name', element)}\""

    raise ToolError(
        f"Action '{action}' failed on element '{element}'. "
        "Use manage_windows(action='inspect') to check available elements and actions."
    )


def set_text(window: str, element: str, text: str) -> str:
    """Set text content of an editable field via AT-SPI."""
    result = _atspi_call(
        {
            "op": "set_text",
            "app": window,
            "element": element,
            "text": text,
        }
    )

    if result.get("error"):
        raise ToolError(result["error"])

    if result.get("found") and result.get("set"):
        el = result.get("element", {})
        return f'Set text on {el.get("role", "?")}: "{el.get("name", element)}"'

    raise ToolError(f"Could not set text on element '{element}'.")


def connect_portal() -> str:
    """Establish a portal session for input control.

    Triggers a one-time KDE authorization dialog. Once approved, all subsequent
    send_input(mode='mouse') calls use the portal for reliable absolute
    pointer positioning.
    """
    portal = _get_portal()
    if portal.is_connected:
        return "Portal session already active."
    result = portal.connect()
    return f"Portal session established: {json.dumps(result)}"


# ---------------------------------------------------------------------------
# Public MCP tools — Dispatchers
# ---------------------------------------------------------------------------


def screenshot(
    target: Literal["desktop", "window", "monitor"] = "window",
    window: str | None = None,
    monitor: str | None = None,
) -> list:
    """Capture the desktop, a window, or a monitor as a compressed JPEG.

    Returns [Image, metadata_text]. The metadata text includes pixel
    coordinates and origin so that send_input(mode='mouse') can map
    image coordinates to absolute screen coordinates.
    """
    global _last_screenshot_meta

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = int(time.time() * 1000)

    if target == "window":
        if window:
            uuid = _resolve_window(window)
            _kwin_activate(uuid)
            time.sleep(0.4)
        jpeg_bytes, meta = capture_active_window()
        jpg_path = SCREENSHOT_DIR / f"capture-{timestamp}.jpg"
        jpg_path.write_bytes(jpeg_bytes)
        _last_screenshot_meta = meta
        caption = meta.get("caption", "Active Window")
        w = meta.get("width", "?")
        h = meta.get("height", "?")
        ox = meta.get("origin_x", 0)
        oy = meta.get("origin_y", 0)
        scale = meta.get("scale", 1.0)
        info = (
            f'Screenshot: "{caption}" ({w}x{h})\n'
            f"Coordinates: origin=({ox}, {oy}), scale={scale}\n"
            f"Use pixel coordinates from this image with send_input(mode=\"mouse\")."
        )
        return [Image(path=str(jpg_path)), info]

    if target == "monitor":
        jpeg_bytes, meta = capture_screen(monitor)
        jpg_path = SCREENSHOT_DIR / f"capture-{timestamp}.jpg"
        jpg_path.write_bytes(jpeg_bytes)
        _last_screenshot_meta = meta
        mon_name = meta.get("monitor", monitor or "unknown")
        w = meta.get("width", "?")
        h = meta.get("height", "?")
        ox = meta.get("origin_x", 0)
        oy = meta.get("origin_y", 0)
        scale = meta.get("scale", 1.0)
        info = (
            f'Screenshot: monitor "{mon_name}" ({w}x{h})\n'
            f"Coordinates: origin=({ox}, {oy}), scale={scale}\n"
            f"Use pixel coordinates from this image with send_input(mode=\"mouse\")."
        )
        return [Image(path=str(jpg_path)), info]

    # target == "desktop" — full desktop via Spectacle
    _last_screenshot_meta = None
    img = _screenshot_desktop()
    return [img, "Screenshot: full desktop\nNo coordinate mapping available for full desktop capture."]


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
    """Send keyboard or mouse input via ydotool (Wayland-native fallback)."""
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
