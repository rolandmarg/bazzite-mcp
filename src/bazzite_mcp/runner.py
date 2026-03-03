import json
import subprocess
from dataclasses import dataclass

from bazzite_mcp.guardrails import check_command


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str
    warning: str | None = None


def run_command(command: str, timeout: int = 120) -> CommandResult:
    check = check_command(command)
    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
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
    command: str,
    tool: str,
    args: dict | None = None,
    rollback: str | None = None,
    timeout: int = 120,
) -> CommandResult:
    """Run a command with audit logging. Use for all mutation operations.

    Args:
        command: shell command to execute
        tool: name of the MCP tool calling this (e.g. 'install_package')
        args: tool arguments as dict (logged as JSON)
        rollback: shell command to undo this action, if known
        timeout: command timeout in seconds
    """
    # Import here to avoid circular import (audit -> db, runner -> audit)
    from bazzite_mcp.audit import AuditLog

    result = run_command(command, timeout=timeout)
    try:
        log = AuditLog()
        log.record(
            tool=tool,
            command=command,
            args=json.dumps(args) if args else None,
            result="success" if result.returncode == 0 else f"failed (exit {result.returncode})",
            output=(result.stdout[:500] if result.stdout else None),
            rollback=rollback,
        )
    except Exception:
        pass  # Don't let audit failures break tool execution
    return result
