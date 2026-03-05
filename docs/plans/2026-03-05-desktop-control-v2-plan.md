# Desktop Control v2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace broken screenshot+input stack with KWin ScreenShot2 + portal D-Bus for reliable desktop control.

**Architecture:** AT-SPI for UI interaction (existing, works), KWin D-Bus for screenshots, portal D-Bus for input injection. No GStreamer, no portal_helper subprocess.

**Tech Stack:** Python, dbus-python, gdbus CLI, Pillow/magick for JPEG compression.

---

### Task 1: KWin ScreenShot2 Helper

**Files:**
- Create: `src/bazzite_mcp/kwin_screenshot.py`
- Test: `tests/test_kwin_screenshot.py`

Implement a module that captures screenshots via KWin's ScreenShot2 D-Bus interface. Returns `(jpeg_bytes, metadata_dict)` where metadata includes `origin_x`, `origin_y`, `width`, `height`, `scale`.

**Functions:**
- `capture_active_window() -> (bytes, dict)` — CaptureActiveWindow, get window geometry from KWin for origin
- `capture_screen(name: str) -> (bytes, dict)` — CaptureScreen with monitor name, origin from kscreen-doctor/KWin
- `capture_active_screen() -> (bytes, dict)` — CaptureActiveScreen
- `capture_area(x, y, w, h) -> (bytes, dict)` — CaptureArea

**Implementation approach:**
1. Use `gdbus call` to invoke `org.kde.KWin.ScreenShot2.CaptureActiveWindow` etc. The pipe fd pattern: create a pipe with `os.pipe()`, pass write-end as fd to D-Bus, read PNG from read-end.
2. Actually, the simplest approach: use the CLI `spectacle` equivalent or `gdbus` with the fd. Since D-Bus fd passing from Python is complex, use the approach of `gdbus call` with `--unix-fd-list` or call via `dbus-python`.
3. Convert PNG→JPEG with Pillow (if available) or `magick` CLI.
4. Get window geometry for origin coords via `qdbus org.kde.KWin /KWin org.kde.KWin.getWindowInfo`.

**Test:** Mock `run_command` calls, verify metadata shape and JPEG output handling.

**Step 1:** Write failing test for `capture_active_window` returning metadata with origin_x, origin_y, scale.
**Step 2:** Implement `capture_active_window` using gdbus/spectacle.
**Step 3:** Write test + implement `capture_screen(name)`.
**Step 4:** Verify PNG→JPEG compression works.
**Step 5:** Commit.

---

### Task 2: Rewrite Portal Client (D-Bus Direct, Input Only)

**Files:**
- Rewrite: `src/bazzite_mcp/portal.py`
- Delete: `src/bazzite_mcp/portal_helper.py` (subprocess no longer needed)
- Test: `tests/test_portal.py`

Rewrite `PortalClient` to use dbus-python directly (no subprocess). Only handles input — no frame capture.

**PortalClient methods:**
- `connect()` — CreateSession → SelectDevices → SelectSources → Start (reuse working D-Bus code from portal_helper.py)
- `pointer_move(x, y)` — NotifyPointerMotionAbsolute
- `click(button, action)` — NotifyPointerButton
- `key_press(keysym)` — NotifyKeyboardKeysym
- `close()` — Session.Close

**Key:** The `connect()` needs dbus-python + GLib main loop which requires system Python. Two options:
- A: Keep a minimal subprocess that just manages the D-Bus session (simpler than portal_helper but no GStreamer)
- B: Use `gdbus call` CLI commands for each operation (no subprocess needed, but Start needs signal handling)

**Recommended: Option A** — thin subprocess that handles the async session creation, then receives input commands. Reuse the working D-Bus session code from current portal_helper.py but strip out all GStreamer/frame capture code. This is proven to work.

**Step 1:** Write failing test for connect + pointer_move.
**Step 2:** Strip portal_helper.py down to session creation + input only (remove all GStreamer code).
**Step 3:** Update portal.py PortalClient to match new helper protocol.
**Step 4:** Commit.

---

### Task 3: Rewrite Screenshot Tool

**Files:**
- Modify: `src/bazzite_mcp/tools/desktop.py`

Replace `_screenshot_desktop()` and `_screenshot_window()` with KWin ScreenShot2 calls. The `screenshot()` MCP tool gets new parameters:

```python
def screenshot(
    target: Literal["window", "monitor", "region"] = "window",
    window: str | None = None,
    monitor: str | None = None,
    x: int | None = None, y: int | None = None,
    width: int | None = None, height: int | None = None,
) -> list:  # Returns [Image, text_metadata]
```

**Behavior:**
- `target="window"` (default): `capture_active_window()` or specific window
- `target="monitor"`: `capture_screen(monitor)` or `capture_active_screen()`
- `target="region"`: `capture_area(x, y, width, height)`

**Response includes metadata text** alongside image:
```
Screenshot captured (active window: "Brave - TradingView")
Coordinates: origin=(200, 100), size=1200x900, scale=1.0
Use these pixel coordinates with send_input for mouse actions.
```

**Step 1:** Write test for new screenshot with metadata.
**Step 2:** Implement using kwin_screenshot module.
**Step 3:** Remove old `_capture_and_compress` / Spectacle code (keep as last-resort fallback).
**Step 4:** Commit.

---

### Task 4: Wire Coordinate Offset Into send_input

**Files:**
- Modify: `src/bazzite_mcp/tools/desktop.py`

Update `_send_mouse()` to store and apply the last screenshot's coordinate metadata.

**Module-level state:**
```python
_last_screenshot_meta: dict | None = None  # {"origin_x": 200, "origin_y": 100, "scale": 1.0}
```

Set by `screenshot()`, read by `send_input()`. The `send_input(mode="mouse", x=335, y=40)` computes:
```python
abs_x = meta["origin_x"] + x / meta["scale"]
abs_y = meta["origin_y"] + y / meta["scale"]
portal.pointer_move(abs_x, abs_y)
```

**Step 1:** Write test verifying coordinate offset is applied.
**Step 2:** Implement state tracking + offset math in `_send_mouse`.
**Step 3:** Commit.

---

### Task 5: Cleanup

**Files:**
- Delete: `src/bazzite_mcp/portal_helper.py` (if fully replaced by Task 2)
- Modify: `src/bazzite_mcp/tools/desktop.py` — remove `_ensure_ydotool_flat_accel`, `_ydotool_move_absolute`, old Spectacle-only code
- Modify: `src/bazzite_mcp/server.py` — verify tool registrations

**Step 1:** Remove dead code.
**Step 2:** Run full test suite.
**Step 3:** Commit.

---

### Task 6: Integration Test

Test the full flow on the live system:
1. `connect_portal` — establish input session
2. `screenshot(target="window", window="brave")` — capture browser window
3. Verify metadata has correct origin coordinates
4. `send_input(mode="mouse", x=<pixel>, y=<pixel>)` — click something visible in the screenshot
5. `screenshot()` — verify the click landed
6. `interact(window="brave", element="...", action="Press")` — test AT-SPI still works

---

## Future Phases (not in scope)

- Phase 2: Smart `click_element(window, description)` tool that combines AT-SPI + vision
- Phase 3: Keyboard input via portal (replace ydotool for typing too)
- Phase 4: Stream mode for rapid capture (keep PipeWire pipeline for gaming/video use cases)
