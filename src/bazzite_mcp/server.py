from fastmcp import FastMCP

from bazzite_mcp.resources import (
    get_docs_index,
    get_server_info,
    get_system_overview,
)
from bazzite_mcp.tools.core import audit, docs, packages, ujust
from bazzite_mcp.tools.containers import (
    manage_distrobox,
    manage_podman,
    manage_quadlet,
)
from bazzite_mcp.tools.desktop import (
    connect_portal,
    interact,
    manage_windows,
    screenshot,
    send_input,
    set_text,
)
from bazzite_mcp.tools.gaming import gaming
from bazzite_mcp.tools.services import (
    manage_firewall,
    manage_network,
    manage_service,
)
from bazzite_mcp.tools.settings import (
    display_config,
    gsettings,
    quick_setting,
)
from bazzite_mcp.tools.system import (
    manage_snapshots,
    storage_diagnostics,
    system_doctor,
    system_info,
)
from bazzite_mcp.tools.virtualization import manage_vm


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

# --- Tools (25 total) ---

# Core
mcp.tool(ujust)
mcp.tool(packages)
mcp.tool(docs)
mcp.tool(audit)

# System
mcp.tool(system_info)
mcp.tool(storage_diagnostics)
mcp.tool(system_doctor)
mcp.tool(manage_snapshots)

# Settings
mcp.tool(quick_setting)
mcp.tool(display_config)
mcp.tool(gsettings)

# Desktop
mcp.tool(connect_portal)
mcp.tool(screenshot)
mcp.tool(manage_windows)
mcp.tool(interact)
mcp.tool(set_text)
mcp.tool(send_input)

# Services & networking
mcp.tool(manage_service)
mcp.tool(manage_firewall)
mcp.tool(manage_network)

# Containers
mcp.tool(manage_distrobox)
mcp.tool(manage_quadlet)
mcp.tool(manage_podman)

# Virtualization
mcp.tool(manage_vm)

# Gaming
mcp.tool(gaming)

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
