from __future__ import annotations

import json
from typing import Any

from bazzite_mcp.runner import ToolError, run_audited

from .shared import VM_OPERATION_STATE_FILE, _utc_timestamp


def _save_operation_state(state: dict[str, Any]) -> None:
    VM_OPERATION_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {**state, "updated_at": _utc_timestamp()}
    VM_OPERATION_STATE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load_operation_state() -> dict[str, Any] | None:
    if not VM_OPERATION_STATE_FILE.exists():
        return None
    try:
        return json.loads(VM_OPERATION_STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {
            "operation": "unknown",
            "state": "failed",
            "error": f"Corrupt operation state file: {VM_OPERATION_STATE_FILE}",
            "updated_at": _utc_timestamp(),
        }


def _format_operation_state() -> list[str]:
    state = _load_operation_state()
    if not state:
        return ["operation", "  state: none"]

    lines = ["operation"]
    lines.append(f"  action: {state.get('operation', 'unknown')}")
    lines.append(f"  state:  {state.get('state', 'unknown')}")
    updated_at = state.get("updated_at")
    if updated_at:
        lines.append(f"  updated: {updated_at}")

    for change in state.get("applied_changes", []):
        lines.append(f"  applied: {change}")

    for warning in state.get("warnings", []):
        lines.append(f"  warning: {warning}")

    error = state.get("error")
    if error:
        lines.append(f"  error: {error}")

    return lines


def _vm_rollback() -> str:
    """Rollback the last prepare operation, if present."""
    state = _load_operation_state()
    if not state:
        return "No VM operation state found. Nothing to roll back."

    rollback_steps = state.get("rollback_steps") or []
    if not rollback_steps:
        return "No rollback steps recorded for the last VM operation."

    failures: list[str] = []
    for step in reversed(rollback_steps):
        label = str(step.get("label", "rollback_step"))
        command = str(step.get("command", "")).strip()
        if not command:
            continue
        result = run_audited(
            command,
            tool="manage_vm",
            args={"action": "rollback", "step": label},
        )
        if result.returncode != 0:
            failures.append(f"{label}: {result.stderr or result.stdout}")

    if failures:
        _save_operation_state(
            {
                **state,
                "state": "failed",
                "error": "Rollback failed: " + "; ".join(failures),
            }
        )
        raise ToolError("rollback_failed: " + "; ".join(failures))

    _save_operation_state(
        {
            **state,
            "state": "rolled_back",
            "applied_changes": [],
            "warnings": [],
            "error": None,
        }
    )
    return "Rollback completed. VM preparation changes were reverted."
