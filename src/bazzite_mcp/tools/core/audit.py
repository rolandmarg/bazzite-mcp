from typing import Literal

from bazzite_mcp.audit import AuditLog
from bazzite_mcp.runner import ToolError, run_audited


def _audit_log_query(
    tool: str | None = None,
    search: str | None = None,
    limit: int = 20,
) -> str:
    """Query the audit log of actions performed by the MCP server."""
    log = AuditLog()
    entries = log.query(tool=tool, search=search, limit=limit)
    if not entries:
        return "No actions recorded yet."

    parts: list[str] = []
    for entry in entries:
        rollback = f"\n  Rollback: {entry['rollback']}" if entry.get("rollback") else ""
        parts.append(
            f"[{entry['timestamp']}] {entry['tool']}: {entry['command']}\n"
            f"  Result: {entry['result']}{rollback}"
        )
    return "\n\n".join(parts)


def _rollback_action(action_id: int) -> str:
    """Execute rollback command for a specific audit entry."""
    log = AuditLog()
    rollback_cmd = log.get_rollback(action_id)
    if not rollback_cmd:
        return f"No rollback command found for action #{action_id}."

    result = run_audited(
        rollback_cmd,
        tool="audit",
        args={"action_id": action_id, "rollback_cmd": rollback_cmd},
    )
    output = f"Rollback command: {rollback_cmd}\n"
    if result.returncode == 0:
        output += f"Success: {result.stdout}"
    else:
        output += f"Failed (exit {result.returncode}): {result.stderr}"
    return output


def audit(
    action: Literal["query", "rollback"],
    action_id: int | None = None,
    tool: str | None = None,
    search: str | None = None,
    limit: int = 20,
) -> str:
    """Query audit log or rollback a previous action."""
    if action == "query":
        return _audit_log_query(tool=tool, search=search, limit=limit)
    if action == "rollback":
        if action_id is None:
            raise ToolError("'action_id' is required for action='rollback'.")
        return _rollback_action(action_id)
    raise ToolError(f"Unknown action '{action}'.")
