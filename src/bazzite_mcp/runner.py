from __future__ import annotations

import json
import logging
import shlex
import subprocess
from collections.abc import Sequence
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


def _normalize_command(command: str | Sequence[str]) -> tuple[list[str], str]:
    if isinstance(command, str):
        argv = shlex.split(command)
        return argv, command
    argv = list(command)
    return argv, shlex.join(argv)


def run_command(
    command: str | Sequence[str],
    timeout: int = 120,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Execute a command with guardrail validation and shell-free subprocess execution.

    String commands are tokenized for compatibility, but execution always uses
    argv with shell=False. New code should pass argv lists directly.
    """
    argv, command_text = _normalize_command(command)
    check = check_command(command_text) if isinstance(command, str) else check_argv(argv)
    result = subprocess.run(
        argv,
        shell=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        env=build_command_env(base=env),
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
    command: str | Sequence[str],
    tool: str,
    args: dict | None = None,
    rollback: str | Sequence[str] | None = None,
    timeout: int = 120,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Run a command with audit logging. Use for all mutation operations.

    Args:
        command: command string or argv list
        tool: name of the MCP tool calling this (e.g. 'install_package')
        args: tool arguments as dict (logged as JSON)
        rollback: rollback command to undo this action, if known
        timeout: command timeout in seconds
    """
    # Import here to avoid circular import (audit -> db, runner -> audit)
    from bazzite_mcp.audit import AuditLog
    from bazzite_mcp.config import load_config

    result = run_command(command, timeout=timeout, env=env)
    try:
        cfg = load_config()
        max_chars = cfg.audit_output_max_chars
        _, cmd_str = _normalize_command(command)
        rollback_str = None
        if rollback is not None:
            _, rollback_str = _normalize_command(rollback)
        log = AuditLog()
        log.record(
            tool=tool,
            command=cmd_str,
            args=json.dumps(args) if args else None,
            result="success"
            if result.returncode == 0
            else f"failed (exit {result.returncode})",
            output=(result.stdout[:max_chars] if result.stdout else None),
            rollback=rollback_str,
        )
    except Exception as exc:
        logger.error(
            "Audit logging failed for tool=%s command=%s: %s", tool, command, exc
        )
        result.warning = (result.warning or "") + f" [AUDIT FAILED: {exc}]"
    return result
