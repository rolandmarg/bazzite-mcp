import importlib

from fastmcp import FastMCP

from bazzite_mcp.resources import (
    get_docs_index,
    get_server_info,
    get_system_overview,
)

mcp = FastMCP(
    "bazzite",
    instructions=(
        "Bazzite OS capability server.\n"
        "Use this server for live system state, explicit host mutations, docs search, audit, and desktop control.\n"
        "Use the repo-local skill 'bazzite-operator' for workflow, policy, and platform reasoning.\n"
        "Use MCP tools when the required capability is available.\n"
        "Audit and rollback support are available for mutating operations."
    ),
)

# --- Auto-discover tools from subpackages ---
# Each subpackage __init__.py exports public tool functions in __all__.
# Names starting with _ are internal helpers and are skipped.

_TOOL_PACKAGES = [
    "bazzite_mcp.tools.core",
    "bazzite_mcp.tools.system",
    "bazzite_mcp.tools.settings",
    "bazzite_mcp.tools.desktop",
    "bazzite_mcp.tools.services",
    "bazzite_mcp.tools.containers",
    "bazzite_mcp.tools.virtualization",
    "bazzite_mcp.tools.gaming",
]

for _pkg_name in _TOOL_PACKAGES:
    _mod = importlib.import_module(_pkg_name)
    for _name in getattr(_mod, "__all__", []):
        if _name.startswith("_"):
            continue
        _obj = getattr(_mod, _name)
        if callable(_obj):
            mcp.tool(_obj)

# --- MCP Resources ---
mcp.resource(
    "bazzite://system/overview",
    description="Current OS, kernel, desktop, and hardware summary",
    mime_type="text/markdown",
)(get_system_overview)
mcp.resource(
    "bazzite://docs/index",
    description="Index of all cached documentation pages with sections and URLs",
    mime_type="text/markdown",
)(get_docs_index)
mcp.resource(
    "bazzite://server/info",
    description="bazzite-mcp server metadata: config, cache status, versions",
    mime_type="text/markdown",
)(get_server_info)
