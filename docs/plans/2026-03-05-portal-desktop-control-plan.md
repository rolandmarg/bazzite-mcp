# Portal Desktop Control — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace broken ydotool mouse + slow Spectacle screenshots with xdg-desktop-portal RemoteDesktop + ScreenCast for reliable input and fast frame capture.

**Architecture:** New `portal.py` module manages a combined RemoteDesktop+ScreenCast session via libportal (GI bindings). Portal runs in system Python (same as AT-SPI) since PyGObject lives in system site-packages. `desktop.py` calls portal for input/screenshots, falling back to ydotool/Spectacle when no portal session exists.

**Tech Stack:** libportal (`gi.repository.Xdp`), GStreamer (`pipewiresrc`), GLib main loop — all via system Python subprocess (same pattern as existing AT-SPI helper).

---

### Task 1: Portal Helper Script

The portal APIs require GLib async + a main loop. Like the AT-SPI helper, we run portal operations via a system Python subprocess that has PyGObject. The helper is a long-running subprocess that communicates via stdin/stdout JSON.

**Files:**
- Create: `src/bazzite_mcp/portal_helper.py` (executed by system Python)
- Test: `tests/test_portal_helper.py`

**Step 1: Write test for portal helper protocol**

```python
# tests/test_portal_helper.py
import json
from unittest.mock import MagicMock, patch

def test_portal_helper_protocol_echo():
    """The helper reads JSON commands from stdin and writes JSON responses to stdout."""
    # We can't test the actual portal (needs display), but we test the protocol
    from bazzite_mcp.portal import _portal_call
    # Tested indirectly in Task 3
    pass
```

Actually — since the portal helper requires a running display session and user authorization, we can't unit test it directly. We'll test the integration layer in Task 3 instead. For now, write the helper script.

**Step 1: Write the portal helper script**

Create `src/bazzite_mcp/portal_helper.py`. This runs as a **long-lived subprocess** under system Python. It:
1. Creates a combined RemoteDesktop+ScreenCast session (triggers KDE auth dialog)
2. Reads JSON commands from stdin, writes JSON responses to stdout
3. Supports: `pointer_move`, `pointer_click`, `key_press`, `grab_frame`, `close`

```python
"""Portal helper — run by system Python as a long-lived subprocess.

Manages an xdg-desktop-portal RemoteDesktop+ScreenCast session.
Reads JSON commands from stdin, writes JSON responses to stdout.

Usage: /usr/bin/python3 -m bazzite_mcp.portal_helper
"""
from __future__ import annotations

import io
import json
import sys
import threading

import gi

gi.require_version("Xdp", "1.0")
gi.require_version("GLib", "2.0")
gi.require_version("Gio", "2.0")
gi.require_version("Gst", "1.0")

from gi.repository import Gio, GLib, Gst, Xdp

Gst.init(None)


class PortalSession:
    """Manages a RemoteDesktop+ScreenCast portal session."""

    def __init__(self) -> None:
        self.portal = Xdp.Portal()
        self.session: Xdp.Session | None = None
        self.loop = GLib.MainLoop()
        self._stream_node_id: int | None = None
        self._pw_fd: int | None = None
        self._error: str | None = None

    def create(self) -> dict:
        """Create session. Blocks until user authorizes via KDE dialog."""
        self._error = None

        self.portal.create_remote_desktop_session_full(
            devices=Xdp.DeviceType.POINTER | Xdp.DeviceType.KEYBOARD,
            outputs=Xdp.OutputType.MONITOR,
            flags=Xdp.RemoteDesktopFlags(0),
            cursor_mode=Xdp.CursorMode.EMBEDDED,
            persist_mode=Xdp.PersistMode.TRANSIENT,
            restore_token=None,
            cancellable=None,
            callback=self._on_session_created,
        )
        self.loop.run()

        if self._error:
            return {"error": self._error}
        if not self.session:
            return {"error": "Session creation failed"}

        # Get stream info for frame capture
        streams = self.session.get_streams()
        if streams and streams.n_children() > 0:
            stream = streams.get_child_value(0)
            self._stream_node_id = stream.get_child_value(0).get_uint32()

        self._pw_fd = self.session.open_pipewire_remote()

        return {
            "status": "active",
            "stream_node_id": self._stream_node_id,
            "pw_fd": self._pw_fd is not None and self._pw_fd >= 0,
        }

    def _on_session_created(self, portal, result, _data=None):
        try:
            self.session = portal.create_remote_desktop_session_finish(result)
            # Start the session (triggers the auth dialog)
            self.session.start(
                parent=None,
                cancellable=None,
                callback=self._on_session_started,
            )
        except Exception as e:
            self._error = str(e)
            self.loop.quit()

    def _on_session_started(self, session, result, _data=None):
        try:
            session.start_finish(result)
        except Exception as e:
            self._error = str(e)
        self.loop.quit()

    def pointer_move(self, stream: int, x: float, y: float) -> dict:
        if not self.session:
            return {"error": "No active session"}
        self.session.pointer_position(stream, x, y)
        return {"ok": True}

    def pointer_click(self, button: int = 272, action: str = "click") -> dict:
        """Send mouse click. button=272 is BTN_LEFT in evdev."""
        if not self.session:
            return {"error": "No active session"}
        self.session.pointer_button(button, Xdp.ButtonState.PRESSED)
        if action != "press":
            import time
            time.sleep(0.02)
            self.session.pointer_button(button, Xdp.ButtonState.RELEASED)
        return {"ok": True}

    def key_press(self, keysym: int, is_keysym: bool = True) -> dict:
        if not self.session:
            return {"error": "No active session"}
        self.session.keyboard_key(is_keysym, keysym, Xdp.KeyState.PRESSED)
        self.session.keyboard_key(is_keysym, keysym, Xdp.KeyState.RELEASED)
        return {"ok": True}

    def grab_frame(self) -> dict:
        """Capture a single frame from the PipeWire stream as JPEG bytes."""
        if self._pw_fd is None or self._stream_node_id is None:
            return {"error": "No PipeWire stream available"}

        import base64
        import subprocess

        # Use GStreamer to grab one frame via pipewiresrc
        # We dup the fd because gstreamer will close it
        import os
        fd = os.dup(self._pw_fd)

        pipeline_str = (
            f"pipewiresrc fd={fd} path={self._stream_node_id} "
            f"do-timestamp=true ! "
            f"videoconvert ! "
            f"videoscale ! video/x-raw,width=2560 ! "
            f"jpegenc quality=85 ! "
            f"appsink name=sink max-buffers=1 drop=true"
        )

        pipeline = Gst.parse_launch(pipeline_str)
        sink = pipeline.get_by_name("sink")
        pipeline.set_state(Gst.State.PLAYING)

        # Pull one frame with timeout
        sample = sink.try_pull_sample(Gst.SECOND * 5)
        pipeline.set_state(Gst.State.NULL)

        if not sample:
            return {"error": "Failed to capture frame within timeout"}

        buf = sample.get_buffer()
        ok, mapinfo = buf.map(Gst.MapFlags.READ)
        if not ok:
            return {"error": "Failed to map buffer"}

        jpeg_b64 = base64.b64encode(mapinfo.data).decode()
        buf.unmap(mapinfo)

        return {"jpeg_b64": jpeg_b64}

    def close(self) -> dict:
        if self.session:
            self.session.close()
            self.session = None
        return {"ok": True}


def main():
    """Main loop: read JSON commands from stdin, write responses to stdout."""
    portal = PortalSession()

    # Signal ready
    sys.stdout.write(json.dumps({"ready": True}) + "\n")
    sys.stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            cmd = json.loads(line)
        except json.JSONDecodeError as e:
            sys.stdout.write(json.dumps({"error": f"Invalid JSON: {e}"}) + "\n")
            sys.stdout.flush()
            continue

        op = cmd.get("op")
        try:
            if op == "create":
                result = portal.create()
            elif op == "pointer_move":
                result = portal.pointer_move(
                    cmd.get("stream", 0), cmd["x"], cmd["y"]
                )
            elif op == "pointer_click":
                result = portal.pointer_click(
                    cmd.get("button", 272), cmd.get("action", "click")
                )
            elif op == "key_press":
                result = portal.key_press(
                    cmd["keysym"], cmd.get("is_keysym", True)
                )
            elif op == "grab_frame":
                result = portal.grab_frame()
            elif op == "close":
                result = portal.close()
            else:
                result = {"error": f"Unknown op: {op}"}
        except Exception as e:
            result = {"error": str(e)}

        sys.stdout.write(json.dumps(result) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
```

**Step 2: Verify the helper script is syntactically valid**

Run: `python3 -c "import ast; ast.parse(open('src/bazzite_mcp/portal_helper.py').read()); print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add src/bazzite_mcp/portal_helper.py
git commit -m "feat: add portal helper subprocess for RemoteDesktop+ScreenCast"
```

---

### Task 2: Portal Client Module

Thin wrapper in `portal.py` that manages the helper subprocess and provides a clean Python API for `desktop.py` to call.

**Files:**
- Create: `src/bazzite_mcp/portal.py`
- Test: `tests/test_portal.py`

**Step 1: Write failing test for portal client**

```python
# tests/test_portal.py
import json
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from bazzite_mcp.portal import PortalClient


class FakeProcess:
    """Mock subprocess for portal_helper."""
    def __init__(self, responses):
        self._responses = iter(responses)
        self.stdin = MagicMock()
        self.stdout = self
        self.pid = 12345
        self.returncode = None
        self._lines = []

    def readline(self):
        return json.dumps(next(self._responses)) + "\n"

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = -15

    def wait(self, timeout=None):
        pass


@patch("bazzite_mcp.portal.subprocess.Popen")
def test_portal_client_connect_creates_session(mock_popen):
    proc = FakeProcess([
        {"ready": True},
        {"status": "active", "stream_node_id": 42, "pw_fd": True},
    ])
    mock_popen.return_value = proc
    client = PortalClient()
    result = client.connect()
    assert result["status"] == "active"
    assert client.is_connected


@patch("bazzite_mcp.portal.subprocess.Popen")
def test_portal_client_pointer_move(mock_popen):
    proc = FakeProcess([
        {"ready": True},
        {"status": "active", "stream_node_id": 42, "pw_fd": True},
        {"ok": True},
    ])
    mock_popen.return_value = proc
    client = PortalClient()
    client.connect()
    result = client.pointer_move(100.0, 200.0)
    assert result["ok"]


@patch("bazzite_mcp.portal.subprocess.Popen")
def test_portal_client_click(mock_popen):
    proc = FakeProcess([
        {"ready": True},
        {"status": "active", "stream_node_id": 42, "pw_fd": True},
        {"ok": True},
    ])
    mock_popen.return_value = proc
    client = PortalClient()
    client.connect()
    result = client.click()
    assert result["ok"]


@patch("bazzite_mcp.portal.subprocess.Popen")
def test_portal_client_not_connected_raises(mock_popen):
    client = PortalClient()
    with pytest.raises(Exception, match="[Nn]ot connected"):
        client.pointer_move(0, 0)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_portal.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bazzite_mcp.portal'`

**Step 3: Write the portal client module**

```python
# src/bazzite_mcp/portal.py
"""Portal client — manages the portal_helper subprocess."""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

from mcp.server.fastmcp.exceptions import ToolError

logger = logging.getLogger(__name__)

_SYSTEM_PYTHON = "/usr/bin/python3"
_HELPER_MODULE = str(Path(__file__).parent / "portal_helper.py")

# Singleton portal client
_client: PortalClient | None = None


def get_portal() -> PortalClient:
    """Get or create the singleton portal client."""
    global _client
    if _client is None:
        _client = PortalClient()
    return _client


class PortalClient:
    """Manages the portal_helper subprocess and provides a sync API."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._stream_node_id: int = 0
        self.is_connected: bool = False

    def connect(self) -> dict:
        """Start helper subprocess and create portal session."""
        if self.is_connected:
            return {"status": "already_active"}

        self._proc = subprocess.Popen(
            [_SYSTEM_PYTHON, _HELPER_MODULE],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Wait for ready signal
        ready = self._read_response()
        if not ready.get("ready"):
            raise ToolError(f"Portal helper failed to start: {ready}")

        # Create the portal session (triggers KDE auth dialog)
        result = self._send({"op": "create"})
        if result.get("error"):
            raise ToolError(f"Portal session failed: {result['error']}")

        self._stream_node_id = result.get("stream_node_id", 0)
        self.is_connected = True
        return result

    def pointer_move(self, x: float, y: float) -> dict:
        self._require_connected()
        return self._send({
            "op": "pointer_move",
            "stream": self._stream_node_id,
            "x": x,
            "y": y,
        })

    def click(self, button: int = 272, action: str = "click") -> dict:
        self._require_connected()
        return self._send({
            "op": "pointer_click",
            "button": button,
            "action": action,
        })

    def key_press(self, keysym: int, is_keysym: bool = True) -> dict:
        self._require_connected()
        return self._send({
            "op": "key_press",
            "keysym": keysym,
            "is_keysym": is_keysym,
        })

    def grab_frame(self) -> dict:
        self._require_connected()
        return self._send({"op": "grab_frame"})

    def close(self) -> None:
        if self._proc and self._proc.poll() is None:
            try:
                self._send({"op": "close"})
            except Exception:
                pass
            self._proc.terminate()
            self._proc.wait(timeout=5)
        self._proc = None
        self.is_connected = False

    def _require_connected(self) -> None:
        if not self.is_connected or not self._proc or self._proc.poll() is not None:
            raise ToolError("Portal not connected. Call connect() first.")

    def _send(self, cmd: dict) -> dict:
        if not self._proc or not self._proc.stdin or not self._proc.stdout:
            raise ToolError("Portal helper process not running.")
        self._proc.stdin.write(json.dumps(cmd) + "\n")
        self._proc.stdin.flush()
        return self._read_response()

    def _read_response(self) -> dict:
        if not self._proc or not self._proc.stdout:
            raise ToolError("Portal helper process not running.")
        line = self._proc.stdout.readline()
        if not line:
            stderr = ""
            if self._proc.stderr:
                stderr = self._proc.stderr.read()
            raise ToolError(f"Portal helper died. stderr: {stderr[:500]}")
        return json.loads(line)
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_portal.py -v`
Expected: 4 passed

**Step 5: Commit**

```bash
git add src/bazzite_mcp/portal.py tests/test_portal.py
git commit -m "feat: add portal client with subprocess management and tests"
```

---

### Task 3: Wire Portal Into Desktop Tools

Replace ydotool mouse and Spectacle screenshot with portal calls. Keep ydotool/Spectacle as fallbacks.

**Files:**
- Modify: `src/bazzite_mcp/tools/desktop.py`
- Modify: `tests/test_tools_desktop.py`

**Step 1: Write tests for portal-backed screenshot and mouse**

Add to `tests/test_tools_desktop.py`:

```python
import base64
from unittest.mock import MagicMock, patch

from bazzite_mcp.tools.desktop import _screenshot_desktop, _send_mouse


@patch("bazzite_mcp.tools.desktop._get_portal")
def test_screenshot_uses_portal_when_connected(mock_get_portal):
    """Portal frame grab is preferred over Spectacle when session is active."""
    fake_jpeg = base64.b64encode(b"\xff\xd8fake_jpeg_data").decode()
    portal = MagicMock()
    portal.is_connected = True
    portal.grab_frame.return_value = {"jpeg_b64": fake_jpeg}
    mock_get_portal.return_value = portal
    result = _screenshot_desktop()
    portal.grab_frame.assert_called_once()
    assert isinstance(result, Image)


@patch("bazzite_mcp.tools.desktop._get_portal")
@patch("bazzite_mcp.tools.desktop.shutil.which")
@patch("bazzite_mcp.tools.desktop.run_command")
def test_screenshot_falls_back_to_spectacle(mock_run, mock_which, mock_get_portal):
    """Falls back to Spectacle when portal is not connected."""
    portal = MagicMock()
    portal.is_connected = False
    mock_get_portal.return_value = portal
    mock_which.return_value = "/usr/bin/spectacle"
    mock_run.return_value = CommandResult(returncode=0, stdout="", stderr="")
    result = _screenshot_desktop()
    assert isinstance(result, Image)
    # Spectacle should have been called
    commands = [c[0][0] for c in mock_run.call_args_list]
    assert any("spectacle" in cmd for cmd in commands)


@patch("bazzite_mcp.tools.desktop._get_portal")
def test_send_mouse_uses_portal_when_connected(mock_get_portal):
    """Portal absolute pointer is used when session is active."""
    portal = MagicMock()
    portal.is_connected = True
    portal.pointer_move.return_value = {"ok": True}
    portal.click.return_value = {"ok": True}
    mock_get_portal.return_value = portal
    result = _send_mouse("click", 500, 300)
    portal.pointer_move.assert_called_once()
    portal.click.assert_called_once()
    assert "500" in result and "300" in result
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tools_desktop.py -v -k portal`
Expected: FAIL — `_get_portal` doesn't exist yet

**Step 3: Modify `desktop.py` to use portal with fallback**

Add near the top of `desktop.py` (after imports):

```python
from bazzite_mcp.portal import get_portal, PortalClient

def _get_portal() -> PortalClient:
    """Get portal client (lazy, may not be connected)."""
    return get_portal()
```

Modify `_screenshot_desktop()`:

```python
def _screenshot_desktop() -> Image:
    """Capture the full desktop."""
    # Try portal frame grab first
    portal = _get_portal()
    if portal.is_connected:
        result = portal.grab_frame()
        if "jpeg_b64" in result:
            import base64
            jpeg_data = base64.b64decode(result["jpeg_b64"])
            SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
            timestamp = int(time.time())
            jpg_path = SCREENSHOT_DIR / f"capture-{timestamp}.jpg"
            jpg_path.write_bytes(jpeg_data)
            return Image(path=str(jpg_path))
    # Fallback to Spectacle
    return _capture_and_compress("--fullscreen")
```

Modify `_send_mouse()` — add portal path at the top, before ydotool:

```python
def _send_mouse(action, x, y, button="left", window=None):
    # Try portal first
    portal = _get_portal()
    if portal.is_connected:
        if window:
            uuid = _resolve_window(window)
            _kwin_activate(uuid)
            time.sleep(0.3)

        portal.pointer_move(float(x), float(y))
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

    # Fallback: ydotool (existing code below)
    sock = _ensure_ydotoold()
    ...
```

**Step 4: Run all desktop tests**

Run: `uv run pytest tests/test_tools_desktop.py -v`
Expected: All pass (old tests still work with Spectacle fallback, new tests verify portal path)

**Step 5: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All 209+ pass

**Step 6: Commit**

```bash
git add src/bazzite_mcp/tools/desktop.py tests/test_tools_desktop.py
git commit -m "feat: wire portal into screenshot and mouse input with fallback"
```

---

### Task 4: Add `connect_portal` MCP Tool

Users need a way to establish the portal session (triggers KDE auth dialog). Add a simple tool for this.

**Files:**
- Modify: `src/bazzite_mcp/tools/desktop.py`
- Modify: `src/bazzite_mcp/server.py`
- Test: `tests/test_tools_desktop.py`

**Step 1: Write failing test**

```python
from bazzite_mcp.tools.desktop import connect_portal

@patch("bazzite_mcp.tools.desktop._get_portal")
def test_connect_portal_creates_session(mock_get_portal):
    portal = MagicMock()
    portal.is_connected = False
    portal.connect.return_value = {"status": "active", "stream_node_id": 42, "pw_fd": True}
    mock_get_portal.return_value = portal
    result = connect_portal()
    assert "active" in result.lower()
    portal.connect.assert_called_once()
```

**Step 2: Run test — expect fail**

Run: `uv run pytest tests/test_tools_desktop.py::test_connect_portal_creates_session -v`

**Step 3: Add `connect_portal` tool to `desktop.py`**

```python
def connect_portal() -> str:
    """Establish a portal session for screen capture and input control.

    Triggers a one-time KDE authorization dialog. Once approved, all subsequent
    screenshot() and send_input(mode='mouse') calls use the portal for reliable
    absolute positioning and fast frame capture.
    """
    portal = _get_portal()
    if portal.is_connected:
        return "Portal session already active."
    result = portal.connect()
    return f"Portal session established: {json.dumps(result)}"
```

Register in `server.py`:

```python
from bazzite_mcp.tools.desktop import (
    connect_portal,
    interact,
    manage_windows,
    screenshot,
    send_input,
    set_text,
)

# Desktop
mcp.tool(connect_portal)
mcp.tool(screenshot)
...
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_tools_desktop.py -v`
Expected: All pass

**Step 5: Commit**

```bash
git add src/bazzite_mcp/tools/desktop.py src/bazzite_mcp/server.py tests/test_tools_desktop.py
git commit -m "feat: add connect_portal MCP tool for session authorization"
```

---

### Task 5: Manual Integration Test

**Step 1: Install and test**

```bash
uv tool install -e .
```

**Step 2: Restart Claude Code MCP connection** (so it picks up the new tool)

**Step 3: Call `connect_portal`** — KDE dialog should appear, click Allow

**Step 4: Test screenshot** — should use portal frame grab (faster)

**Step 5: Test mouse click** — should use portal absolute positioning (accurate)

**Step 6: Verify the TradingView dropdown click works**

```
send_input(mode="mouse", x=1200, y=150, window="TradingView")
```

**Step 7: If all works, commit and push**

```bash
git push
```

---

### Task 6: Clean Up Ydotool Workarounds

After portal is confirmed working, clean up the dead code.

**Files:**
- Modify: `src/bazzite_mcp/tools/desktop.py`

**Step 1: Remove `_ensure_ydotool_flat_accel` and `_ydotool_move_absolute`**

These were workaround attempts for the broken ydotool absolute positioning. With portal, they're unnecessary.

**Step 2: Keep ydotool keyboard/type functions** as fallback for `send_input(mode="type")` and `send_input(mode="key")` until Task 7 (Phase 2).

**Step 3: Run tests, commit**

```bash
uv run pytest tests/ -v
git add src/bazzite_mcp/tools/desktop.py
git commit -m "refactor: remove ydotool mouse workarounds, portal handles input"
```

---

## Phase 2 (Future)

### Task 7: Portal Keyboard Input

Replace ydotool `type`/`key` with portal `keyboard_key`. Requires mapping key names to X11 keysyms. Lower priority — ydotool keyboard already works fine.

## Phase 3 (Future)

### Task 8: Semantic Click Tool

New MCP tool: `click_element(window, label)` — combines AT-SPI tree search with portal click. Finds element by label/role, gets its screen coordinates, clicks via portal. Zero vision tokens for structured UIs.
