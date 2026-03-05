#!/usr/bin/env python3
"""Portal helper subprocess for RemoteDesktop via D-Bus.

Long-lived process: reads JSON commands from stdin, writes JSON responses
to stdout (one object per line).  Executed by system Python which has
PyGObject / dbus-python bindings.

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

  {"op": "close"}
      Tear down session and exit.
"""
from __future__ import annotations

import json
import sys
import traceback
from typing import Any

import dbus
import dbus.mainloop.glib
import gi

from gi.repository import GLib  # noqa: E402

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PORTAL_BUS = "org.freedesktop.portal.Desktop"
_PORTAL_PATH = "/org/freedesktop/portal/desktop"
_RD_IFACE = "org.freedesktop.portal.RemoteDesktop"
_SC_IFACE = "org.freedesktop.portal.ScreenCast"
_REQ_IFACE = "org.freedesktop.portal.Request"

# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------

_bus: dbus.SessionBus | None = None
_session_path: str | None = None
_streams: list[dict] | None = None


# ---------------------------------------------------------------------------
# Helpers — stdout protocol
# ---------------------------------------------------------------------------


def _respond(obj: dict[str, Any]) -> None:
    """Write a single JSON line to stdout and flush."""
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _error(msg: str) -> None:
    _respond({"error": msg})


def _sender_token() -> str:
    """D-Bus sender name munged for portal handle paths."""
    assert _bus is not None
    return _bus.get_unique_name().replace(".", "_").lstrip(":")


# ---------------------------------------------------------------------------
# Session creation via D-Bus (step-by-step portal protocol)
# ---------------------------------------------------------------------------


def _create_session() -> dict[str, Any]:
    """Create a combined RemoteDesktop+ScreenCast session.

    Walks through the full portal handshake:
      CreateSession → SelectDevices → SelectSources → Start
    Uses a GLib main loop to wait for each async Response signal.
    """
    global _bus, _session_path, _streams

    _bus = dbus.SessionBus()
    portal = _bus.get_object(_PORTAL_BUS, _PORTAL_PATH)
    rd = dbus.Interface(portal, _RD_IFACE)
    sc = dbus.Interface(portal, _SC_IFACE)

    sender = _sender_token()
    loop = GLib.MainLoop()
    result: dict[str, Any] = {}
    step = [0]

    def on_response(response_code, results):
        global _session_path, _streams
        nonlocal result
        step[0] += 1

        if response_code != 0:
            result = {"error": f"Portal denied at step {step[0]} (code={response_code})"}
            loop.quit()
            return

        try:
            if step[0] == 1:
                # CreateSession done → SelectDevices
                session_h = str(results.get("session_handle", ""))
                _bus.add_signal_receiver(
                    on_response, "Response", _REQ_IFACE, _PORTAL_BUS,
                    f"/org/freedesktop/portal/desktop/request/{sender}/sel_dev",
                )
                rd.SelectDevices(
                    dbus.ObjectPath(session_h),
                    {"handle_token": "sel_dev", "types": dbus.UInt32(3)},
                )

            elif step[0] == 2:
                # SelectDevices done → SelectSources (ScreenCast on RD session)
                session_h = f"/org/freedesktop/portal/desktop/session/{sender}/portal_sess"
                _bus.add_signal_receiver(
                    on_response, "Response", _REQ_IFACE, _PORTAL_BUS,
                    f"/org/freedesktop/portal/desktop/request/{sender}/sel_src",
                )
                sc.SelectSources(
                    dbus.ObjectPath(session_h),
                    {
                        "handle_token": "sel_src",
                        "types": dbus.UInt32(1),       # MONITOR
                        "cursor_mode": dbus.UInt32(2),  # EMBEDDED
                        "multiple": False,
                    },
                )

            elif step[0] == 3:
                # SelectSources done → Start (triggers user dialog)
                session_h = f"/org/freedesktop/portal/desktop/session/{sender}/portal_sess"
                _bus.add_signal_receiver(
                    on_response, "Response", _REQ_IFACE, _PORTAL_BUS,
                    f"/org/freedesktop/portal/desktop/request/{sender}/start_rd",
                )
                rd.Start(dbus.ObjectPath(session_h), "", {"handle_token": "start_rd"})

            elif step[0] == 4:
                # Start done → extract streams
                session_h = f"/org/freedesktop/portal/desktop/session/{sender}/portal_sess"

                raw_streams: list[dict] = []
                streams_var = results.get("streams", dbus.Array([], signature="(ua{sv})"))
                for i, entry in enumerate(streams_var):
                    node_id = int(entry[0])
                    props = dict(entry[1]) if len(entry) > 1 else {}
                    s: dict[str, Any] = {"node_id": node_id, "index": i}
                    if "size" in props:
                        sz = props["size"]
                        s["width"] = int(sz[0])
                        s["height"] = int(sz[1])
                    raw_streams.append(s)

                if not raw_streams:
                    result = {"error": "No streams in Start response"}
                    loop.quit()
                    return

                _session_path = session_h
                _streams = raw_streams

                result = {"ok": True, "streams": raw_streams}
                loop.quit()

        except Exception as exc:
            result = {"error": f"Step {step[0]} error: {exc}"}
            loop.quit()

    # Step 1: CreateSession
    _bus.add_signal_receiver(
        on_response, "Response", _REQ_IFACE, _PORTAL_BUS,
        f"/org/freedesktop/portal/desktop/request/{sender}/create_sess",
    )
    rd.CreateSession({
        "session_handle_token": "portal_sess",
        "handle_token": "create_sess",
    })

    # 60s timeout for user to approve dialog
    GLib.timeout_add_seconds(60, lambda: (loop.quit(), False))
    loop.run()

    if not result:
        result = {"error": "Timed out waiting for portal session"}

    return result


# ---------------------------------------------------------------------------
# Input simulation via D-Bus
# ---------------------------------------------------------------------------


def _pointer_move(stream: int, x: float, y: float) -> dict[str, Any]:
    if _bus is None or _session_path is None:
        return {"error": "No active session"}
    portal = _bus.get_object(_PORTAL_BUS, _PORTAL_PATH)
    rd = dbus.Interface(portal, _RD_IFACE)
    rd.NotifyPointerMotionAbsolute(
        dbus.ObjectPath(_session_path),
        dbus.Dictionary({}, signature="sv"),
        dbus.UInt32(stream),
        dbus.Double(x),
        dbus.Double(y),
    )
    return {"ok": True}


def _pointer_click(button: int = 272, action: str = "click") -> dict[str, Any]:
    if _bus is None or _session_path is None:
        return {"error": "No active session"}
    portal = _bus.get_object(_PORTAL_BUS, _PORTAL_PATH)
    rd = dbus.Interface(portal, _RD_IFACE)
    sp = dbus.ObjectPath(_session_path)
    opts = dbus.Dictionary({}, signature="sv")
    btn = dbus.Int32(button)
    pressed = dbus.UInt32(1)
    released = dbus.UInt32(0)

    if action == "press":
        rd.NotifyPointerButton(sp, opts, btn, pressed)
    elif action == "release":
        rd.NotifyPointerButton(sp, opts, btn, released)
    else:  # "click"
        rd.NotifyPointerButton(sp, opts, btn, pressed)
        rd.NotifyPointerButton(sp, opts, btn, released)

    return {"ok": True}


def _key_press(keysym: int, is_keysym: bool = True) -> dict[str, Any]:
    if _bus is None or _session_path is None:
        return {"error": "No active session"}
    portal = _bus.get_object(_PORTAL_BUS, _PORTAL_PATH)
    rd = dbus.Interface(portal, _RD_IFACE)
    sp = dbus.ObjectPath(_session_path)
    opts = dbus.Dictionary({}, signature="sv")
    pressed = dbus.UInt32(1)
    released = dbus.UInt32(0)

    if is_keysym:
        rd.NotifyKeyboardKeysym(sp, opts, dbus.Int32(keysym), pressed)
        rd.NotifyKeyboardKeysym(sp, opts, dbus.Int32(keysym), released)
    else:
        rd.NotifyKeyboardKeycode(sp, opts, dbus.Int32(keysym), pressed)
        rd.NotifyKeyboardKeycode(sp, opts, dbus.Int32(keysym), released)

    return {"ok": True}


# ---------------------------------------------------------------------------
# Session teardown
# ---------------------------------------------------------------------------


def _close_session() -> dict[str, Any]:
    global _session_path, _streams, _bus
    if _session_path is not None and _bus is not None:
        try:
            session_obj = _bus.get_object(_PORTAL_BUS, _session_path)
            session_iface = dbus.Interface(session_obj, "org.freedesktop.portal.Session")
            session_iface.Close()
        except Exception:
            pass
        _session_path = None
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
