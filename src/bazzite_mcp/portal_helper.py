#!/usr/bin/env python3
"""Portal helper subprocess for RemoteDesktop + ScreenCast via libportal.

Long-lived process: reads JSON commands from stdin, writes JSON responses
to stdout (one object per line).  Executed by system Python which has
PyGObject / GStreamer / libportal bindings.

Protocol
--------
On startup prints ``{"ready": true}`` then waits for commands.

Commands (one JSON object per line on stdin):
  {"op": "create"}
      Create a combined RemoteDesktop+ScreenCast session.
      Triggers the KDE portal auth dialog; blocks until approved/denied.
      Returns {"ok": true, "streams": [...]} or {"error": "..."}.

  {"op": "pointer_move", "stream": <int>, "x": <float>, "y": <float>}
  {"op": "pointer_click", "button": 272, "action": "click"|"press"|"release"}
  {"op": "key_press", "keysym": <int>, "is_keysym": true}
  {"op": "grab_frame"}
      Capture a single JPEG frame from the PipeWire stream.
      Returns {"ok": true, "jpeg_b64": "..."}.

  {"op": "close"}
      Tear down session and exit.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import traceback
from typing import Any

import gi

gi.require_version("Gst", "1.0")
gi.require_version("Xdp", "1.0")

from gi.repository import GLib, Gst, Xdp  # noqa: E402

Gst.init(None)

# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------

_portal: Xdp.Portal | None = None
_session: Xdp.Session | None = None
_loop: GLib.MainLoop | None = None
_streams: list[dict] | None = None
_pw_fd: int | None = None  # PipeWire fd (dup'd for reuse)


# ---------------------------------------------------------------------------
# Helpers — stdout protocol
# ---------------------------------------------------------------------------


def _respond(obj: dict[str, Any]) -> None:
    """Write a single JSON line to stdout and flush."""
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _error(msg: str) -> None:
    _respond({"error": msg})


# ---------------------------------------------------------------------------
# Session creation (async via GLib main loop)
# ---------------------------------------------------------------------------


def _create_session() -> dict[str, Any]:
    """Create a combined RemoteDesktop+ScreenCast session.

    Runs a temporary GLib main loop until the async callback fires.
    Returns a result dict.
    """
    global _portal, _session, _streams, _pw_fd

    _portal = Xdp.Portal()
    result: dict[str, Any] = {}
    loop = GLib.MainLoop()

    def _on_session_created(portal: Xdp.Portal, async_result: Any, _user_data: Any) -> None:
        nonlocal result
        try:
            session = portal.create_remote_desktop_session_full_finish(async_result)
            if session is None:
                result = {"error": "Session creation returned None (user denied?)"}
                loop.quit()
                return

            global _session, _streams, _pw_fd
            _session = session

            # Parse streams GLib.Variant -> list of dicts
            streams_variant = session.get_streams()
            raw_streams: list[dict] = []
            if streams_variant is not None:
                n = streams_variant.n_children()
                for i in range(n):
                    child = streams_variant.get_child_value(i)
                    node_id = child.get_child_value(0).get_uint32()
                    raw_streams.append({"node_id": node_id, "index": i})
            _streams = raw_streams

            # Get PipeWire fd and dup it (portal may close the original)
            pw_fd_raw = session.open_pipewire_remote()
            if pw_fd_raw < 0:
                result = {"error": f"open_pipewire_remote returned {pw_fd_raw}"}
                loop.quit()
                return
            _pw_fd = os.dup(pw_fd_raw)
            os.close(pw_fd_raw)

            result = {"ok": True, "streams": raw_streams}
        except Exception as exc:
            result = {"error": f"Session callback error: {exc}"}
        finally:
            loop.quit()

    devices = Xdp.DeviceType.POINTER | Xdp.DeviceType.KEYBOARD
    outputs = Xdp.OutputType.MONITOR
    flags = Xdp.RemoteDesktopFlags.NONE
    cursor_mode = Xdp.CursorMode.EMBEDDED
    persist_mode = Xdp.PersistMode.TRANSIENT

    _portal.create_remote_desktop_session_full(
        devices,
        outputs,
        flags,
        cursor_mode,
        persist_mode,
        None,   # restore_token
        None,   # cancellable
        _on_session_created,
        None,   # user_data
    )

    loop.run()
    return result


# ---------------------------------------------------------------------------
# Input simulation
# ---------------------------------------------------------------------------


def _pointer_move(stream: int, x: float, y: float) -> dict[str, Any]:
    if _session is None:
        return {"error": "No active session"}
    _session.pointer_position(stream, x, y)
    return {"ok": True}


def _pointer_click(
    button: int = 272,
    action: str = "click",
) -> dict[str, Any]:
    if _session is None:
        return {"error": "No active session"}

    pressed = Xdp.ButtonState.PRESSED
    released = Xdp.ButtonState.RELEASED

    if action == "press":
        _session.pointer_button(button, pressed)
    elif action == "release":
        _session.pointer_button(button, released)
    else:  # "click"
        _session.pointer_button(button, pressed)
        _session.pointer_button(button, released)

    return {"ok": True}


def _key_press(keysym: int, is_keysym: bool = True) -> dict[str, Any]:
    if _session is None:
        return {"error": "No active session"}
    _session.keyboard_key(is_keysym, keysym, Xdp.KeyState.PRESSED)
    _session.keyboard_key(is_keysym, keysym, Xdp.KeyState.RELEASED)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Frame capture via GStreamer
# ---------------------------------------------------------------------------


def _grab_frame() -> dict[str, Any]:
    """Capture a single JPEG frame from the PipeWire stream."""
    if _session is None or _pw_fd is None or not _streams:
        return {"error": "No active session or no streams"}

    node_id = _streams[0]["node_id"]

    # Dup the fd — GStreamer's pipewiresrc will close it
    fd_for_gst = os.dup(_pw_fd)

    pipeline_str = (
        f"pipewiresrc fd={fd_for_gst} path={node_id} do-timestamp=true ! "
        f"videoconvert ! videoscale ! video/x-raw,width=2560 ! "
        f"jpegenc quality=85 ! appsink name=sink max-buffers=1 drop=true"
    )

    pipeline = Gst.parse_launch(pipeline_str)
    if pipeline is None:
        os.close(fd_for_gst)
        return {"error": "Failed to create GStreamer pipeline"}

    sink = pipeline.get_by_name("sink")
    if sink is None:
        os.close(fd_for_gst)
        return {"error": "Failed to find appsink in pipeline"}

    # Set to emit-signals=False so we use pull-sample
    sink.set_property("emit-signals", False)

    pipeline.set_state(Gst.State.PLAYING)

    # Wait up to 5 seconds for a frame
    sample = None
    try:
        sample = sink.try_pull_sample(5 * Gst.SECOND)
    except Exception as exc:
        pipeline.set_state(Gst.State.NULL)
        return {"error": f"pull_sample failed: {exc}"}

    if sample is None:
        pipeline.set_state(Gst.State.NULL)
        return {"error": "No frame received within timeout"}

    buf = sample.get_buffer()
    ok, map_info = buf.map(Gst.MapFlags.READ)
    if not ok:
        pipeline.set_state(Gst.State.NULL)
        return {"error": "Failed to map GStreamer buffer"}

    jpeg_bytes = bytes(map_info.data)
    buf.unmap(map_info)
    pipeline.set_state(Gst.State.NULL)

    jpeg_b64 = base64.b64encode(jpeg_bytes).decode("ascii")
    return {"ok": True, "jpeg_b64": jpeg_b64}


# ---------------------------------------------------------------------------
# Session teardown
# ---------------------------------------------------------------------------


def _close_session() -> dict[str, Any]:
    global _session, _pw_fd, _streams
    if _session is not None:
        try:
            _session.close()
        except Exception:
            pass
        _session = None
    if _pw_fd is not None:
        try:
            os.close(_pw_fd)
        except OSError:
            pass
        _pw_fd = None
    _streams = None
    return {"ok": True}


# ---------------------------------------------------------------------------
# Main command loop
# ---------------------------------------------------------------------------


def main() -> None:
    _respond({"ready": True})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            cmd = json.loads(line)
        except json.JSONDecodeError as exc:
            _error(f"Invalid JSON: {exc}")
            continue

        op = cmd.get("op")
        try:
            if op == "create":
                result = _create_session()
            elif op == "pointer_move":
                result = _pointer_move(
                    stream=cmd.get("stream", 0),
                    x=float(cmd.get("x", 0)),
                    y=float(cmd.get("y", 0)),
                )
            elif op == "pointer_click":
                result = _pointer_click(
                    button=int(cmd.get("button", 272)),
                    action=cmd.get("action", "click"),
                )
            elif op == "key_press":
                result = _key_press(
                    keysym=int(cmd["keysym"]),
                    is_keysym=bool(cmd.get("is_keysym", True)),
                )
            elif op == "grab_frame":
                result = _grab_frame()
            elif op == "close":
                result = _close_session()
                _respond(result)
                break
            else:
                result = {"error": f"Unknown op: {op}"}
            _respond(result)
        except Exception:
            _error(traceback.format_exc())


if __name__ == "__main__":
    main()
