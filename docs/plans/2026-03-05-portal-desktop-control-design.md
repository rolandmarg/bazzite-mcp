# Portal-Based Desktop Control for AI Agents

## Problem

Current desktop control in bazzite-mcp uses ydotool (broken absolute positioning on Wayland) and Spectacle screenshots (slow, ~1s per capture). This makes UI automation unreliable and impractical for multi-step workflows.

## Design

Replace ydotool+Spectacle with xdg-desktop-portal APIs (RemoteDesktop + ScreenCast) for input and frame capture, keeping AT-SPI as the primary structured UI reader.

## Architecture

```
MCP tool layer (unchanged public API)
  |
  +-- Input:   portal RemoteDesktop session
  |            NotifyPointerMotionAbsolute, NotifyPointerButton,
  |            NotifyKeyboardKeycode/Keysym
  |
  +-- Read:    AT-SPI accessibility tree (existing, cheap)    <-- primary
  +-- Read:    portal ScreenCast -> PipeWire frame grab       <-- fallback
  +-- Query:   KWin D-Bus (window list, geometry, focus)      <-- existing
```

## Components

### 1. Portal Session Manager (`portal.py`)

Manages a combined RemoteDesktop+ScreenCast session via D-Bus:
- `create_session()` — creates portal session, triggers KDE authorization dialog once
- `send_pointer_absolute(x, y)` — absolute pointer positioning (logical coords)
- `send_click(button)` — mouse button press/release
- `send_key(keycode)` — keyboard input
- `grab_frame() -> Image` — grab single frame from PipeWire stream
- `close()` — cleanup

Session lifecycle:
- Created lazily on first input/screenshot call
- Persists for the MCP server's lifetime (no re-auth per action)
- One-time KDE dialog: "bazzite-mcp wants to control input and share screen" -> Allow

### 2. PipeWire Frame Capture

Use GStreamer pipeline (`pipewiresrc`) to grab single frames on demand:
- Open PipeWire remote FD from ScreenCast portal
- On `grab_frame()`: pull one frame, convert to JPEG, return
- No continuous streaming — only captures when AI requests it
- Same token cost as current Spectacle approach, but ~10x faster (no subprocess, no disk)

### 3. Tool Integration

Existing MCP tools stay the same from the caller's perspective:

- `screenshot()` — uses portal frame grab instead of Spectacle (falls back to Spectacle if no session)
- `send_input(mode="mouse")` — uses portal absolute pointer instead of ydotool
- `send_input(mode="key/type")` — uses portal keyboard instead of ydotool
- `interact()` / `set_text()` — AT-SPI unchanged (already works, preferred for structured UI)

### 4. Fallback Chain

Portal unavailable? Graceful degradation:
1. Portal session active -> use portal input + frame grab
2. Portal unavailable -> fall back to ydotool (with fixed coords) + Spectacle
3. AT-SPI always available as structured UI reader regardless

## Dependencies

All already present on the system:
- `libportal` (GI bindings: `gi.require_version('Xdp', '1.0')`)
- `GStreamer` with `pipewiresrc` element
- `xdg-desktop-portal-kde` (handles the auth dialog)
- System Python with PyGObject (already used for AT-SPI)

No new packages to install.

## Authorization Flow

1. First MCP tool call that needs input/vision triggers `create_session()`
2. KDE shows dialog: "bazzite-mcp requests screen sharing and remote input"
3. User clicks Allow (once per MCP server lifetime)
4. All subsequent calls use the established session

## Token Efficiency

- AT-SPI tree inspection: ~1-5K tokens (text) — use for navigating known UI
- Portal frame grab: ~100-200K tokens (image) — use only when AT-SPI insufficient
- Tool recommends AT-SPI first in responses, vision as verification/fallback

## What Gets Removed

- ydotool dependency for mouse input (keep for keyboard typing as fallback)
- Spectacle dependency for screenshots (keep as fallback)
- All DPI/coordinate math hacks — portal handles this natively

## Scope

Phase 1: Portal session + absolute mouse input + frame grab (replaces broken mouse + slow screenshots)
Phase 2: Portal keyboard input (replaces ydotool keyboard)
Phase 3: Smart tool that combines AT-SPI + vision for "click the button labeled X" semantic actions
