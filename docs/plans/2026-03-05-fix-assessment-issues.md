# Fix Assessment Issues — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Address all issues identified in the bazzite-mcp assessment: drop portal, add argv/shell=False support, auto-discovery, error taxonomy, audit truncation, guardrails refinement, and rewrite screenshot + send_input.

**Architecture:** Dual-mode runner (str→shell=True, list→shell=False). Guardrails get `check_argv()` for list-based validation. Server.py auto-discovers tools. Desktop tools rewritten to use argv and drop portal dependency.

**Tech Stack:** Python 3.11+, FastMCP, subprocess, sqlite3

---

### Task 1: Drop Portal

**Files:**
- Delete: `src/bazzite_mcp/portal.py`
- Delete: `src/bazzite_mcp/portal_helper.py`
- Modify: `src/bazzite_mcp/tools/desktop/__init__.py` — remove connect_portal export
- Modify: `src/bazzite_mcp/tools/desktop/shared.py` — remove portal import
- Modify: `src/bazzite_mcp/tools/desktop/capture.py` — remove connect_portal function and portal import
- Modify: `src/bazzite_mcp/server.py` — remove connect_portal registration
- Delete: `tests/test_portal.py`
- Modify: `tests/test_tools_desktop.py` — remove connect_portal test

**Step 1: Remove portal files**
```bash
rm src/bazzite_mcp/portal.py src/bazzite_mcp/portal_helper.py tests/test_portal.py
```

**Step 2: Update shared.py** — remove portal import, keep only constants:
```python
from __future__ import annotations
from pathlib import Path

SCREENSHOT_DIR = Path("/tmp/bazzite-mcp")
YDOTOOL_SOCKET = SCREENSHOT_DIR / "ydotool.sock"
```

**Step 3: Update capture.py** — remove `connect_portal` function and `_get_portal` import.

**Step 4: Update desktop/__init__.py** — remove `connect_portal` from imports and `__all__`.

**Step 5: Update server.py** — remove `connect_portal` from imports and `mcp.tool(connect_portal)`.

**Step 6: Update test_tools_desktop.py** — remove `test_connect_portal_creates_session` and the connect_portal import.

**Step 7: Run tests**
```bash
uv run pytest tests/ -v
```

**Step 8: Commit**
```bash
git add -A && git commit -m "chore: drop portal (portal.py, portal_helper.py, connect_portal tool)"
```

---

### Task 2: Add Structured Error Types

**Files:**
- Create: `src/bazzite_mcp/errors.py`
- Modify: `src/bazzite_mcp/runner.py` — use CommandError for failed commands

**Step 1: Create errors.py**
```python
"""Structured error types for bazzite-mcp tools."""
from __future__ import annotations
from mcp.server.fastmcp.exceptions import ToolError


class CommandError(ToolError):
    """A command execution failed with structured context."""

    def __init__(
        self,
        message: str,
        *,
        returncode: int | None = None,
        stdout: str = "",
        stderr: str = "",
        command: str | list[str] | None = None,
    ) -> None:
        detail = message
        if stderr:
            detail = f"{message}\nstderr: {stderr}"
        super().__init__(detail)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.command = command


class TimeoutError(CommandError):
    """A command exceeded its timeout."""

    def __init__(self, command: str | list[str], timeout: int) -> None:
        super().__init__(
            f"Command timed out after {timeout}s",
            returncode=124,
            command=command,
        )
        self.timeout = timeout
```

**Step 2: Run tests**
**Step 3: Commit**

---

### Task 3: Guardrails — Add argv Support and Fix Patterns

**Files:**
- Modify: `src/bazzite_mcp/guardrails.py` — add `check_argv()`, split metacharacter pattern
- Create: `tests/test_guardrails_argv.py`

**Step 1: Add check_argv to guardrails.py**

Add after existing `check_command`:
```python
# Patterns that apply to argv arguments (not shell-level)
BLOCKED_ARGV_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("rm", re.compile(r"^/$|^/\*$"), "destructive filesystem operation"),
    ("dd", re.compile(r"^of=/dev/"), "destructive disk write"),
    ("mkfs", re.compile(r""), "destructive filesystem operation"),  # any mkfs use
    ("shred", re.compile(r""), "destructive file operation"),
    ("wipefs", re.compile(r""), "destructive disk operation"),
    ("chmod", re.compile(r"^[0-7]*777$"), "world-writable permissions are blocked"),
    ("chown", re.compile(r"^root$"), "changing ownership to root is blocked"),
]

BLOCKED_BINARIES = frozenset({
    "curl", "wget", "nc", "ncat", "eval", "bash", "sh",
})


def check_argv(argv: list[str]) -> CheckResult:
    """Validate a command given as an argv list (for shell=False execution)."""
    if not argv:
        raise GuardrailError("Blocked: empty command")

    binary = argv[0].rsplit("/", 1)[-1]

    if binary in BLOCKED_BINARIES:
        raise GuardrailError(f"Blocked: '{binary}' is not allowed")

    if binary not in ALLOWED_COMMAND_PREFIXES:
        raise GuardrailError(
            f"Blocked: command '{binary}' is not in the allowed command list"
        )

    # Check argv-level blocked patterns
    for target_bin, pattern, reason in BLOCKED_ARGV_PATTERNS:
        if not binary.startswith(target_bin):
            continue
        for arg in argv[1:]:
            if pattern.pattern == "" or pattern.search(arg):
                raise GuardrailError(f"Blocked: {reason}")

    # Hostname length check
    if binary == "hostnamectl" and "set-hostname" in argv:
        idx = argv.index("set-hostname")
        if idx + 1 < len(argv):
            hostname = argv[idx + 1].strip("'\"")
            if len(hostname) > 20:
                raise GuardrailError(
                    f"Blocked: hostname '{hostname}' exceeds 20 characters (breaks Distrobox)"
                )

    # rpm-ostree checks
    if binary == "rpm-ostree":
        if "reset" in argv:
            raise GuardrailError("Blocked: destructive: removes ALL layered packages")
        if "rebase" in argv:
            rest = " ".join(argv)
            if re.search(r"gnome|kde|plasma|sway|hyprland|cosmic", rest):
                raise GuardrailError(
                    "Blocked: Do NOT rebase to switch desktop environments."
                )
        if "install" in argv:
            return CheckResult(
                allowed=True,
                warning="rpm-ostree is a LAST RESORT on Bazzite.",
            )

    # systemctl mask check
    if binary == "systemctl" and ("mask" in argv or "unmask" in argv):
        raise GuardrailError("Blocked: masking services is blocked for safety")

    return CheckResult(allowed=True)
```

**Step 2: Write tests for check_argv**
**Step 3: Run tests**
**Step 4: Commit**

---

### Task 4: Runner Dual Mode (str | list)

**Files:**
- Modify: `src/bazzite_mcp/runner.py` — accept `str | list[str]`, use shell=False for lists
- Modify: `tests/test_runner.py` — add argv tests

**Step 1: Update run_command signature and logic**
```python
def run_command(command: str | list[str], timeout: int = 120) -> CommandResult:
    if isinstance(command, list):
        check = check_argv(command)
        result = subprocess.run(
            command,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env=build_command_env(),
        )
    else:
        check = check_command(command)
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env=build_command_env(),
        )
    stdout = result.stdout.strip()
    if check.warning:
        stdout = f"WARNING: {check.warning}\n\n{stdout}"
    return CommandResult(
        returncode=result.returncode,
        stdout=stdout,
        stderr=result.stderr.strip(),
        warning=check.warning,
    )
```

**Step 2: Update run_audited signature**
```python
def run_audited(
    command: str | list[str],
    tool: str,
    args: dict | None = None,
    rollback: str | None = None,
    timeout: int = 120,
) -> CommandResult:
```
Update the audit record to store command as string: `" ".join(command) if isinstance(command, list) else command`.
Use `config.audit_output_max_chars` instead of hardcoded 500.

**Step 3: Add tests for argv mode**
**Step 4: Run tests**
**Step 5: Commit**

---

### Task 5: Increase Audit Output Truncation

**Files:**
- Modify: `src/bazzite_mcp/config.py` — change default `audit_output_max_chars` from 500 to 2000
- Modify: `src/bazzite_mcp/runner.py` — use config value instead of hardcoded 500

**Step 1: Update config default**
Change line 65: `audit_output_max_chars: int = 2000`

**Step 2: Update runner.py to use config**
In `run_audited`, replace `result.stdout[:500]` with:
```python
from bazzite_mcp.config import load_config
cfg = load_config()
output=(result.stdout[:cfg.audit_output_max_chars] if result.stdout else None),
```

**Step 3: Run tests**
**Step 4: Commit**

---

### Task 6: Auto-Discovery in server.py

**Files:**
- Modify: `src/bazzite_mcp/server.py` — replace manual imports with auto-discovery
- Modify: `tests/test_tool_registration.py` — verify auto-discovered tools

**Step 1: Rewrite server.py**

Each tool subpackage __init__.py already exports its public tool functions. Scan for them:
```python
import importlib
import inspect
from fastmcp import FastMCP
from bazzite_mcp.resources import get_docs_index, get_server_info, get_system_overview

mcp = FastMCP(
    "bazzite",
    instructions=(
        "Bazzite OS capability server.\n"
        "Use this server for live system state, explicit host mutations, docs search, audit, and desktop control.\n"
        "Use the repo-local skill 'bazzite-operator' for workflow, policy, and platform reasoning.\n"
        "Use MCP tools when the required capability is available.\n"
        "Audit and rollback support are available for mutating operations."
    ),
)

# Auto-discover tools from subpackages
_TOOL_PACKAGES = [
    "bazzite_mcp.tools.core",
    "bazzite_mcp.tools.system",
    "bazzite_mcp.tools.settings",
    "bazzite_mcp.tools.desktop",
    "bazzite_mcp.tools.services",
    "bazzite_mcp.tools.containers",
    "bazzite_mcp.tools.virtualization",
    "bazzite_mcp.tools.gaming",
]

for pkg_name in _TOOL_PACKAGES:
    mod = importlib.import_module(pkg_name)
    for name in getattr(mod, "__all__", []):
        if name.startswith("_"):
            continue
        obj = getattr(mod, name)
        if callable(obj):
            mcp.tool(obj)

# MCP Resources
mcp.resource(
    "bazzite://system/overview",
    description="Current OS, kernel, desktop, and hardware summary",
    mime_type="text/markdown",
)(get_system_overview)
mcp.resource(
    "bazzite://docs/index",
    description="Index of all cached documentation pages with sections and URLs",
    mime_type="text/markdown",
)(get_docs_index)
mcp.resource(
    "bazzite://server/info",
    description="bazzite-mcp server metadata: config, cache status, versions",
    mime_type="text/markdown",
)(get_server_info)
```

**Step 2: Verify tool count hasn't changed** (should be 24 now, minus connect_portal).

**Step 3: Update test_tool_registration.py**
```python
import asyncio
from bazzite_mcp.server import mcp

def test_all_tools_registered() -> None:
    tools = asyncio.run(mcp.list_tools())
    tool_names = {t.name for t in tools}
    # Verify key tools are present
    assert "packages" in tool_names
    assert "docs" in tool_names
    assert "system_info" in tool_names
    assert "screenshot" in tool_names
    assert "manage_vm" in tool_names
    # Portal tool should NOT be registered
    assert "connect_portal" not in tool_names
    assert len(tool_names) >= 24
```

**Step 4: Run tests**
**Step 5: Commit**

---

### Task 7: Rewrite Screenshot (capture.py + kwin_screenshot.py)

**Files:**
- Modify: `src/bazzite_mcp/kwin_screenshot.py` — use argv, clean up
- Modify: `src/bazzite_mcp/tools/desktop/capture.py` — remove portal, use argv, simplify
- Modify: `tests/test_kwin_screenshot.py` — update for argv
- Modify: `tests/test_tools_desktop.py` — update screenshot tests

The rewrite goals:
1. Use `list[str]` argv for spectacle and magick commands (shell=False)
2. Remove portal dependency from capture.py
3. Remove module-level `_last_screenshot_meta` global — return metadata in the response string instead
4. Clean up kwin_screenshot.py to be the single capture implementation

**Step 1: Rewrite kwin_screenshot.py**

Key changes:
- `run_command(["spectacle", "-a", "--background", "--nonotify", "--output", str(png_path)])` instead of f-string
- `run_command(["magick", str(png_path), "-quality", "85", str(jpg_path)])` instead of f-string
- `run_command(["kscreen-doctor", "--outputs"])` instead of string
- `run_command(["gdbus", "call", "--session", ...])` instead of string
- `run_command(["magick", "identify", "-format", "%w %h", str(path)])` instead of string

**Step 2: Rewrite capture.py**

Key changes:
- Remove `from .shared import _get_portal`
- Remove `connect_portal` function entirely
- Remove `_last_screenshot_meta` global. Instead, embed metadata in the info string returned alongside the Image.
- Use argv for all run_command calls
- Simplify the screenshot function:

```python
from __future__ import annotations

import json
import time
from typing import Literal

from fastmcp.utilities.types import Image
from mcp.server.fastmcp.exceptions import ToolError

from bazzite_mcp.desktop_env import format_graphical_error
from bazzite_mcp.kwin_screenshot import capture_screen
from bazzite_mcp.runner import run_command
from .shared import SCREENSHOT_DIR
from .windows import _kwin_activate, _resolve_window


def screenshot(
    target: Literal["desktop", "window", "monitor"] = "window",
    window: str | None = None,
    monitor: str | None = None,
):
    """Capture the desktop, a window, or a monitor as a compressed JPEG.

    Returns an image and metadata string with coordinates for use with send_input.
    """
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = int(time.time() * 1000)

    if target == "window":
        if window:
            uuid = _resolve_window(window)
            _kwin_activate(uuid)
            time.sleep(0.4)

        png_path = SCREENSHOT_DIR / f"win-{timestamp}.png"
        jpg_path = png_path.with_suffix(".jpg")

        result = run_command([
            "spectacle", "-a", "--background", "--nonotify", "--output", str(png_path),
        ])
        if result.returncode != 0:
            raise ToolError(format_graphical_error("Spectacle capture failed", result.stderr))

        img_path = _convert_to_jpeg(png_path, jpg_path)
        return [Image(path=str(img_path)), f"Screenshot: active window"]

    jpeg_bytes, meta = capture_screen(monitor)
    jpg_path = SCREENSHOT_DIR / f"capture-{timestamp}.jpg"
    jpg_path.write_bytes(jpeg_bytes)

    info = (
        f"Screenshot: monitor \"{meta.get('monitor', 'unknown')}\" "
        f"({meta.get('width', '?')}x{meta.get('height', '?')})\n"
        f"origin=({meta.get('origin_x', 0)}, {meta.get('origin_y', 0)}), "
        f"scale={meta.get('scale', 1.0)}\n"
        f"Use pixel coordinates from this image with send_input(mode='mouse').\n"
        f"metadata={json.dumps(meta)}"
    )
    return [Image(path=str(jpg_path)), info]


def _convert_to_jpeg(png_path, jpg_path, quality: int = 85):
    """Convert PNG to JPEG, return the path of the resulting image."""
    conv = run_command(["magick", str(png_path), "-quality", str(quality), str(jpg_path)])
    if conv.returncode != 0:
        return png_path  # fallback to PNG
    png_path.unlink(missing_ok=True)
    return jpg_path
```

**Step 3: Update send_input** to parse metadata from screenshot info string instead of using global. (Done in Task 8.)

**Step 4: Update tests**
**Step 5: Run tests**
**Step 6: Commit**

---

### Task 8: Rewrite send_input (input.py)

**Files:**
- Modify: `src/bazzite_mcp/tools/desktop/input.py` — use argv, remove custom _shell_quote, clean up coordinate handling
- Modify: `tests/test_tools_desktop.py` — update input tests

Key changes:
1. Use `run_command(["ydotool", ...])` argv style instead of string concat
2. Remove custom `_shell_quote` — not needed with shell=False
3. Ydotool needs `YDOTOOL_SOCKET` env var — pass via env parameter or prepend to argv
4. Since ydotool uses env var, keep string mode for ydotool commands (env var prefix requires shell). OR set env var in the subprocess env dict.
5. Accept optional `metadata` parameter (JSON string) for coordinate offset instead of cross-module global
6. Clean up `_ensure_ydotoold` — use argv for the Popen call (already does)

**Step 1: Rewrite input.py**

```python
from __future__ import annotations

import json
import shutil
import subprocess
import time
from typing import Literal

from mcp.server.fastmcp.exceptions import ToolError

from bazzite_mcp.desktop_env import build_command_env
from bazzite_mcp.runner import run_command
from .shared import SCREENSHOT_DIR, YDOTOOL_SOCKET
from .windows import _kwin_activate, _resolve_window


def _ensure_ydotoold() -> str:
    """Ensure ydotoold daemon is running. Returns socket path."""
    if not shutil.which("ydotoold"):
        raise ToolError("ydotoold is not installed. Install ydotool for input simulation.")

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


def _ydotool_env(sock: str) -> dict[str, str]:
    """Build env dict with YDOTOOL_SOCKET set."""
    env = build_command_env()
    env["YDOTOOL_SOCKET"] = sock
    return env


def _run_ydotool(argv: list[str], sock: str) -> subprocess.CompletedProcess:
    """Run a ydotool command with the socket env set."""
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=10,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        env=_ydotool_env(sock),
    )


def _focus_window(window: str | None) -> None:
    """Activate a window by name if specified."""
    if window:
        uuid = _resolve_window(window)
        _kwin_activate(uuid)
        time.sleep(0.3)


def _get_virtual_desktop_size() -> tuple[int, int]:
    """Get the logical virtual desktop size from monitor geometry."""
    from bazzite_mcp.kwin_screenshot import get_monitor_info
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
    result = _run_ydotool(["ydotool", "type", "--key-delay", "12", "--", keys], sock)
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
    """Send mouse input via ydotool with coordinate scaling."""
    sock = _ensure_ydotoold()
    _focus_window(window)

    # Apply coordinate offset from screenshot metadata
    if screenshot_meta:
        abs_x = screenshot_meta.get("origin_x", 0) + x / screenshot_meta.get("scale", 1.0)
        abs_y = screenshot_meta.get("origin_y", 0) + y / screenshot_meta.get("scale", 1.0)
    else:
        abs_x, abs_y = float(x), float(y)

    vw, vh = _get_virtual_desktop_size()
    yd_x = int(abs_x / vw * 32767)
    yd_y = int(abs_y / vh * 32767)

    _run_ydotool(["ydotool", "mousemove", "--absolute", "-x", str(yd_x), "-y", str(yd_y)], sock)
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
```

**Step 2: Update desktop/__init__.py** — remove `_send_mouse` from exports (it's internal).

**Step 3: Update tests**
**Step 4: Run tests**
**Step 5: Commit**

---

### Task 9: Update All Tests

**Files:**
- Modify: `tests/test_tools_desktop.py` — update for rewritten screenshot/input
- Modify: `tests/test_kwin_screenshot.py` — update for argv
- Modify: `tests/test_runner.py` — add argv tests
- Modify: `tests/test_security.py` — verify argv guardrails

**Step 1: Update test_runner.py** — add test for list-based commands:
```python
def test_run_argv_command() -> None:
    result = run_command(["echo", "hello"])
    assert result.returncode == 0
    assert "hello" in result.stdout

def test_run_argv_blocked() -> None:
    with pytest.raises(GuardrailError):
        run_command(["curl", "http://evil.com"])
```

**Step 2: Update test_tools_desktop.py** — fix mock targets for argv calls.

**Step 3: Update test_kwin_screenshot.py** — mock calls now receive lists not strings.

**Step 4: Run full test suite**
```bash
uv run pytest tests/ -v
```

**Step 5: Commit**
