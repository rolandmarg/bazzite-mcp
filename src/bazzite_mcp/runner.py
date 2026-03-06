from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass

from bazzite_mcp.desktop_env import build_command_env
from mcp.server.fastmcp.exceptions import ToolError

from bazzite_mcp.guardrails import check_argv, check_command

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str
    warning: str | None = None


def run_command(command: str | list[str], timeout: int = 120) -> CommandResult:
    """Execute a command with guardrail validation.

    Accepts either a shell string (shell=True) or an argv list (shell=False).
    Using argv lists is preferred — it eliminates shell injection by design.
    """
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
    # Surface guardrail warnings directly in output so they always reach the user
    if check.warning:
        stdout = f"WARNING: {check.warning}\n\n{stdout}"
    return CommandResult(
        returncode=result.returncode,
        stdout=stdout,
        stderr=result.stderr.strip(),
        warning=check.warning,
    )


def run_audited(
    command: str | list[str],
    tool: str,
    args: dict | None = None,
    rollback: str | None = None,
    timeout: int = 120,
) -> CommandResult:
    """Run a command with audit logging. Use for all mutation operations.

    Args:
        command: shell command string or argv list
        tool: name of the MCP tool calling this (e.g. 'install_package')
        args: tool arguments as dict (logged as JSON)
        rollback: shell command to undo this action, if known
        timeout: command timeout in seconds
    """
    # Import here to avoid circular import (audit -> db, runner -> audit)
    from bazzite_mcp.audit import AuditLog
    from bazzite_mcp.config import load_config

    result = run_command(command, timeout=timeout)
    try:
        cfg = load_config()
        max_chars = cfg.audit_output_max_chars
        cmd_str = " ".join(command) if isinstance(command, list) else command
        log = AuditLog()
        log.record(
            tool=tool,
            command=cmd_str,
            args=json.dumps(args) if args else None,
            result="success"
            if result.returncode == 0
            else f"failed (exit {result.returncode})",
            output=(result.stdout[:max_chars] if result.stdout else None),
            rollback=rollback,
        )
    except Exception as exc:
        logger.error(
            "Audit logging failed for tool=%s command=%s: %s", tool, command, exc
        )
        result.warning = (result.warning or "") + f" [AUDIT FAILED: {exc}]"
    return result
