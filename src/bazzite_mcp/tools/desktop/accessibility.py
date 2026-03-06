from __future__ import annotations

import json
import subprocess
from pathlib import Path

from mcp.server.fastmcp.exceptions import ToolError

from bazzite_mcp.desktop_env import build_command_env

_SYSTEM_PYTHON = "/usr/bin/python3"
_ATSPI_HELPER_PATH = Path(__file__).with_name("atspi_helper.py")


def _atspi_call(cmd: dict) -> dict:
    """Call the checked-in AT-SPI helper via system Python and return parsed JSON."""
    result = subprocess.run(
        [_SYSTEM_PYTHON, str(_ATSPI_HELPER_PATH), json.dumps(cmd)],
        capture_output=True,
        text=True,
        timeout=10,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        env=build_command_env(),
    )
    if result.returncode != 0:
        raise ToolError(f"AT-SPI query failed: {result.stderr.strip()}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ToolError(f"AT-SPI returned invalid JSON: {result.stdout[:200]}") from exc


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
        element_info = result.get("element", {})
        return f"Performed '{action}' on {element_info.get('role', '?')}: \"{element_info.get('name', element)}\""

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
        element_info = result.get("element", {})
        return f'Set text on {element_info.get("role", "?")}: "{element_info.get("name", element)}"'

    raise ToolError(f"Could not set text on element '{element}'.")
