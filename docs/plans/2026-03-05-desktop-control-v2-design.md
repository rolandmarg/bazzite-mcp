# Desktop Control v2 Design

## Problem
Current desktop tools are unreliable: ydotool coordinates broken on Wayland, portal GStreamer pipeline returns combined multi-monitor stream (5120x1609) where screenshot pixels ≠ input coordinates, clicks never land correctly.

## Design: AT-SPI First, Vision Fallback

### Screenshot — KWin ScreenShot2 D-Bus
No portal session needed. Direct D-Bus call → PNG file descriptor.
- `CaptureActiveWindow(options, pipe)` — default, smallest image
- `CaptureScreen(name, options, pipe)` — per-monitor (HDMI-A-1, HDMI-A-2)
- `CaptureActiveScreen(options, pipe)` — monitor with focused window
- `CaptureArea(x, y, w, h, options, pipe)` — arbitrary region

Returns native resolution. Response includes `origin_x`, `origin_y` (logical coords of top-left corner) so `send_input` can auto-offset. Compress to JPEG before returning to model.

### Input — Portal RemoteDesktop (lazy)
Portal session created on first `send_input` call, kept alive. Uses D-Bus directly (not libportal).
- `NotifyPointerMotionAbsolute(session, opts, stream, x, y)` — logical coords
- `NotifyPointerButton(session, opts, button, state)`
- `NotifyKeyboardKeysym(session, opts, keysym, state)`

### Coordinate Mapping (transparent to model)
1. `screenshot(target="window")` returns image + `{"origin_x": 200, "origin_y": 100, "scale": 1.0}`
2. Model sees image, identifies pixel `(335, 40)` in screenshot
3. Model calls `send_input(mode="mouse", x=335, y=40)`
4. Tool computes: `portal_x = origin_x + x / scale`, `portal_y = origin_y + y / scale`
5. If scale != 1.0 (HiDPI monitor), screenshot pixels are physical but portal uses logical — divide by scale

### Tool Surface
| Tool | Method | Cost |
|------|--------|------|
| `manage_windows` | KWin D-Bus + AT-SPI | Text only |
| `interact` | AT-SPI action | Text only |
| `set_text` | AT-SPI editable text | Text only |
| `screenshot` | KWin ScreenShot2 | Image (~800 tiles for window) |
| `send_input` | Portal RemoteDesktop / ydotool fallback | Text only |
| `connect_portal` | Portal session setup | Text only |

### What Gets Removed
- GStreamer/PipeWire frame capture pipeline
- portal_helper.py subprocess (replace with direct D-Bus in portal.py)
- ydotool for mouse (keep as keyboard fallback only)
- Combined desktop capture
- All DPI coordinate hacks

### Dependencies (all pre-installed)
- `qdbus` / `gdbus` for KWin ScreenShot2
- `dbus-python` for portal RemoteDesktop session
- `Pillow` or `magick` for PNG→JPEG compression
- AT-SPI via system Python (existing)
