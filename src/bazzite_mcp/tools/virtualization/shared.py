from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bazzite_mcp.runner import ToolError

VM_STORAGE_DIR = Path.home() / ".local" / "share" / "bazzite-mcp" / "vms"
VM_OPERATION_STATE_FILE = VM_STORAGE_DIR.parent / "vm_operation_state.json"
DEFAULT_DISK_GB = 64


@dataclass(frozen=True)
class AtomicStep:
    label: str
    command: str
    rollback: str | None = None
    rollback_on_failure: bool = False


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_vm_name(name: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        raise ToolError(
            "Invalid VM name. Use only letters, digits, dot, underscore, and dash."
        )


def _resolve_iso_path(iso_path: str) -> Path:
    path = Path(iso_path).expanduser()
    if not path.is_file():
        raise ToolError(f"ISO path does not exist or is not a file: {path}")
    if path.suffix.lower() != ".iso":
        raise ToolError(f"Install media must be an .iso file: {path}")
    return path


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
