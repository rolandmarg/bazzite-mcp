from __future__ import annotations

from typing import Literal

from bazzite_mcp.runner import ToolError

from .lifecycle import (
    _create_default_vm,
    _snapshot_create,
    _snapshot_list,
    _snapshot_revert,
    _vm_control,
    _vm_delete,
    _vm_list,
    _vm_prepare,
    _vm_preflight,
    _vm_setup,
    _vm_status,
)
from .state import _vm_rollback

__all__ = ["manage_vm"]


def manage_vm(
    action: Literal[
        "setup",
        "prepare",
        "preflight",
        "rollback",
        "status",
        "list",
        "create_default",
        "start",
        "stop",
        "delete",
        "snapshot_list",
        "snapshot_create",
        "snapshot_revert",
    ],
    name: str | None = None,
    iso_path: str | None = None,
    snapshot: str | None = None,
    ram_mb: int | None = None,
    vcpus: int | None = None,
    disk_gb: int | None = None,
    delete_storage: bool = False,
    require_iommu: bool = False,
) -> str:
    """Manage VMs on Bazzite with hardened default profile support."""
    if action == "prepare":
        return _vm_prepare()
    if action == "preflight":
        return _vm_preflight(iso_path=iso_path, require_iommu=require_iommu)
    if action == "rollback":
        return _vm_rollback()
    if action == "setup":
        return _vm_setup()
    if action == "status":
        return _vm_status()
    if action == "list":
        return _vm_list()
    if action == "create_default":
        if not name:
            raise ToolError("'name' is required for action='create_default'.")
        if not iso_path:
            raise ToolError("'iso_path' is required for action='create_default'.")
        return _create_default_vm(name, iso_path, ram_mb, vcpus, disk_gb)
    if action in ("start", "stop"):
        if not name:
            raise ToolError(f"'name' is required for action='{action}'.")
        return _vm_control(name, action)
    if action == "delete":
        if not name:
            raise ToolError("'name' is required for action='delete'.")
        return _vm_delete(name, delete_storage)
    if action == "snapshot_list":
        if not name:
            raise ToolError("'name' is required for action='snapshot_list'.")
        return _snapshot_list(name)
    if action == "snapshot_create":
        if not name:
            raise ToolError("'name' is required for action='snapshot_create'.")
        return _snapshot_create(name, snapshot)
    if action == "snapshot_revert":
        if not name:
            raise ToolError("'name' is required for action='snapshot_revert'.")
        if not snapshot:
            raise ToolError("'snapshot' is required for action='snapshot_revert'.")
        return _snapshot_revert(name, snapshot)
    raise ToolError(f"Unknown action '{action}'.")
