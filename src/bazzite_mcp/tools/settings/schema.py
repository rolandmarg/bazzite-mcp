from __future__ import annotations

import shlex
from typing import Literal

from bazzite_mcp.runner import ToolError, run_audited, run_command


def _get_settings(schema: str, key: str) -> str:
    """Read a gsettings value."""
    result = run_command(f"gsettings get {shlex.quote(schema)} {shlex.quote(key)}")
    if result.returncode != 0:
        raise ToolError(f"Error reading {schema} {key}: {result.stderr}")
    return result.stdout


def _set_settings(schema: str, key: str, value: str) -> str:
    """Write a gsettings value."""
    result = run_audited(
        f"gsettings set {shlex.quote(schema)} {shlex.quote(key)} {shlex.quote(value)}",
        tool="gsettings",
        args={"schema": schema, "key": key, "value": value},
    )
    if result.returncode != 0:
        raise ToolError(f"Error setting {schema} {key}: {result.stderr}")
    return f"Set {schema} {key} = {value}"


def gsettings(
    action: Literal["get", "set"],
    schema: str | None = None,
    key: str | None = None,
    value: str | None = None,
) -> str:
    """Read or write a gsettings value."""
    if not schema or not key:
        raise ToolError("'schema' and 'key' are required.")
    if action == "get":
        return _get_settings(schema, key)
    if action == "set":
        if value is None:
            raise ToolError("'value' is required for action='set'.")
        return _set_settings(schema, key, value)
    raise ToolError(f"Unknown action '{action}'.")
