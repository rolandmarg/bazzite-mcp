import importlib

from fastmcp import FastMCP

from bazzite_mcp.resources import (
    get_dev_environments,
    get_game_optimization,
    get_install_policy,
    get_knowledge_index,
    get_server_info,
    get_system_overview,
    get_tool_routing,
    get_troubleshooting,
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
    "bazzite://knowledge/index",
    description="Index of built-in Bazzite knowledge resources and official sources",
    mime_type="text/markdown",
)(get_knowledge_index)
mcp.resource(
    "bazzite://knowledge/install-policy",
    description="Bazzite-native install policy guidance",
    mime_type="text/markdown",
)(get_install_policy)
mcp.resource(
    "bazzite://knowledge/tool-routing",
    description="Map tasks to MCP execution versus skill reasoning",
    mime_type="text/markdown",
)(get_tool_routing)
mcp.resource(
    "bazzite://knowledge/troubleshooting",
    description="Troubleshooting guidance for common Bazzite host issues",
    mime_type="text/markdown",
)(get_troubleshooting)
mcp.resource(
    "bazzite://knowledge/dev-environments",
    description="Guidance for host, container, and VM development environments",
    mime_type="text/markdown",
)(get_dev_environments)
mcp.resource(
    "bazzite://knowledge/game-optimization",
    description="Gaming and optimization guidance for Bazzite systems",
    mime_type="text/markdown",
)(get_game_optimization)
mcp.resource(
    "bazzite://server/info",
    description="bazzite-mcp server metadata: config, cache status, versions",
    mime_type="text/markdown",
)(get_server_info)
