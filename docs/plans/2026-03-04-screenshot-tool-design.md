# Screenshot Tool Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `screenshot` MCP tool that captures the full desktop and returns a compressed, AI-vision-ready image path.

**Architecture:** New `desktop.py` tool module using `spectacle` for capture and `magick` for JPEG compression. Follows existing tool patterns — plain function, returns str, uses `run_command` from runner.py. Read-only, no audit logging.

**Tech Stack:** spectacle (KDE), imagemagick (`magick`), Python stdlib (shutil, time, os, pathlib)

---

### Task 1: Write the failing test for screenshot tool

**Files:**
- Create: `tests/test_tools_desktop.py`

**Step 1: Write the test file**

```python
from unittest.mock import MagicMock, patch, call
import os

from bazzite_mcp.runner import CommandResult
from bazzite_mcp.tools.desktop import screenshot


@patch("bazzite_mcp.tools.desktop.shutil.which")
@patch("bazzite_mcp.tools.desktop.run_command")
def test_screenshot_returns_jpeg_path(mock_run: MagicMock, mock_which: MagicMock) -> None:
    mock_which.return_value = "/usr/bin/spectacle"  # spectacle found
    mock_run.return_value = CommandResult(returncode=0, stdout="", stderr="")
    result = screenshot()
    assert result.endswith(".jpg")
    assert "/tmp/bazzite-mcp/" in result


@patch("bazzite_mcp.tools.desktop.shutil.which")
@patch("bazzite_mcp.tools.desktop.run_command")
def test_screenshot_calls_spectacle_then_magick(mock_run: MagicMock, mock_which: MagicMock) -> None:
    mock_which.return_value = "/usr/bin/spectacle"
    mock_run.return_value = CommandResult(returncode=0, stdout="", stderr="")
    screenshot()
    commands = [c[0][0] for c in mock_run.call_args_list]
    assert any("spectacle" in cmd for cmd in commands)
    assert any("magick" in cmd for cmd in commands)


@patch("bazzite_mcp.tools.desktop.shutil.which")
def test_screenshot_raises_when_spectacle_missing(mock_which: MagicMock) -> None:
    mock_which.return_value = None
    try:
        screenshot()
        assert False, "Should have raised"
    except Exception as e:
        assert "spectacle" in str(e).lower()


@patch("bazzite_mcp.tools.desktop.shutil.which")
@patch("bazzite_mcp.tools.desktop.run_command")
def test_screenshot_falls_back_to_png_without_magick(mock_run: MagicMock, mock_which: MagicMock) -> None:
    def which_side_effect(name: str) -> str | None:
        return "/usr/bin/spectacle" if name == "spectacle" else None
    mock_which.side_effect = which_side_effect
    mock_run.return_value = CommandResult(returncode=0, stdout="", stderr="")
    result = screenshot()
    assert result.endswith(".png")
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kira/bazzite-mcp && .venv/bin/pytest tests/test_tools_desktop.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bazzite_mcp.tools.desktop'`

**Step 3: Commit**

```bash
cd /home/kira/bazzite-mcp
git add tests/test_tools_desktop.py
git commit -m "test: add failing tests for screenshot tool"
```

---

### Task 2: Implement the screenshot tool

**Files:**
- Create: `src/bazzite_mcp/tools/desktop.py`

**Step 1: Write the implementation**

```python
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from mcp.server.fastmcp.exceptions import ToolError

from bazzite_mcp.runner import run_command

SCREENSHOT_DIR = Path("/tmp/bazzite-mcp")


def screenshot() -> str:
    """Capture the full desktop and return a compressed, AI-vision-ready JPEG path.

    Uses Spectacle (KDE) for capture and ImageMagick for JPEG compression.
    Falls back to raw PNG if ImageMagick is not available.
    """
    if not shutil.which("spectacle"):
        raise ToolError(
            "spectacle is not installed. "
            "It should be pre-installed on Bazzite KDE — check your image."
        )

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = int(time.time())
    png_path = SCREENSHOT_DIR / f"screenshot-{timestamp}.png"
    jpg_path = SCREENSHOT_DIR / f"screenshot-{timestamp}.jpg"

    result = run_command(
        f"spectacle --fullscreen --background --nonotify --output {png_path}"
    )
    if result.returncode != 0:
        raise ToolError(f"Spectacle capture failed: {result.stderr}")

    if not shutil.which("magick"):
        return str(png_path)

    result = run_command(
        f"magick {png_path} -resize 2560x -quality 75 {jpg_path}"
    )
    if result.returncode != 0:
        return str(png_path)

    png_path.unlink(missing_ok=True)
    return str(jpg_path)
```

**Step 2: Run tests to verify they pass**

Run: `cd /home/kira/bazzite-mcp && .venv/bin/pytest tests/test_tools_desktop.py -v`
Expected: All 4 tests PASS

**Step 3: Commit**

```bash
cd /home/kira/bazzite-mcp
git add src/bazzite_mcp/tools/desktop.py
git commit -m "feat: add screenshot tool for AI-vision desktop capture"
```

---

### Task 3: Register the tool in server.py

**Files:**
- Modify: `src/bazzite_mcp/server.py:53-60` (add import)
- Modify: `src/bazzite_mcp/server.py:126` (add registration after process_list)

**Step 1: Add import**

Add after the system imports (line 60):

```python
from bazzite_mcp.tools.desktop import screenshot
```

**Step 2: Add tool registration**

Add after `mcp.tool(process_list)` (line 126):

```python
mcp.tool(screenshot)
```

**Step 3: Run full test suite**

Run: `cd /home/kira/bazzite-mcp && .venv/bin/pytest -v`
Expected: All tests PASS including existing registration tests

**Step 4: Commit**

```bash
cd /home/kira/bazzite-mcp
git add src/bazzite_mcp/server.py
git commit -m "feat: register screenshot tool in MCP server"
```

---

### Task 4: Smoke test with live MCP server

**Step 1: Restart the MCP server**

The server runs via stdio transport from Claude Code's config. Restart Claude Code or the MCP connection to pick up the new tool.

**Step 2: Call the tool**

Use `mcp__bazzite__screenshot()` — it should return a JPEG path under `/tmp/bazzite-mcp/`.

**Step 3: Verify the image**

Use the Read tool on the returned path to visually confirm the screenshot captured the desktop correctly.
