from fastmcp import FastMCP

from bazzite_mcp.resources import (
    get_docs_index,
    get_install_hierarchy,
    get_install_policy_resource,
    get_server_info,
    get_system_overview,
)
from bazzite_mcp.tools.audit_tools import audit
from bazzite_mcp.tools.containers import (
    manage_distrobox,
    manage_podman,
    manage_quadlet,
)
from bazzite_mcp.tools.desktop import (
    interact,
    manage_windows,
    screenshot,
    send_input,
    set_text,
)
from bazzite_mcp.tools.docs import docs
from bazzite_mcp.tools.gaming import gaming
from bazzite_mcp.tools.packages import packages
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
from bazzite_mcp.tools.ujust import ujust
from bazzite_mcp.tools.virtualization import manage_vm


mcp = FastMCP(
    "bazzite",
    instructions=(
        "Bazzite OS management server. Key principles:\n"
        "1. Always check ujust first for system operations (ujust_list, ujust_show, ujust_run)\n"
        "2. Follow the 6-tier install hierarchy: ujust > flatpak > brew > distrobox > AppImage > rpm-ostree\n"
        "3. Use query_bazzite_docs to search cached documentation\n"
        "4. Every mutation is audit-logged with rollback support — check audit_log_query to review actions\n"
        "5. For containers: prefer distrobox for dev environments, quadlet for persistent services\n"
        "6. For untrusted executables, prefer virtual machines over containers; manage_vm provides safe defaults\n"
        "7. rpm-ostree install is a LAST RESORT — it can freeze updates and block rebasing\n"
        "8. For gaming: use steam_library to find games, game_reports for community optimization data, "
        "game_settings to apply MangoHud/launch options. Use hardware_info + game_reports to make "
        "hardware-aware recommendations. Existing manage_service covers GameMode."
    ),
)

# --- Tools (24 total) ---

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
    "bazzite://install/hierarchy",
    description="Bazzite's 6-tier install hierarchy with per-category recommendations",
    mime_type="text/markdown",
)(get_install_hierarchy)
mcp.resource(
    "bazzite://install/policy",
    description="Quick-reference install policy (ujust > flatpak > brew > distrobox > AppImage > rpm-ostree)",
    mime_type="text/plain",
)(get_install_policy_resource)
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


# --- MCP Prompts ---
@mcp.prompt()
def troubleshoot_system(symptom: str) -> str:
    """Gather diagnostics for a system issue."""
    return (
        f"The user is experiencing: {symptom}\n\n"
        "Diagnostic steps:\n"
        "1. Run system_info(detail='basic') to get OS/kernel/desktop\n"
        "2. Use bash: journalctl -n 50 -p err to find errors\n"
        "3. Run system_info(detail='full') if hardware-related\n"
        "4. Run manage_service(action='status', name=<service>) for relevant services\n"
        "5. Search docs with docs(action='search', query=<topic>)\n"
        "6. Use bash: rpm-ostree status for pending OS updates\n\n"
        "Provide a summary of findings and recommended fixes."
    )


@mcp.prompt()
def install_app(app_name: str) -> str:
    """Walk through the 6-tier install hierarchy to find and install an app."""
    return (
        f"Install '{app_name}' following Bazzite's 6-tier hierarchy:\n\n"
        "1. First, run packages(action='search', package=<name>) to check ujust, flatpak, and brew\n"
        "2. If found in ujust (Tier 1), use ujust(action='run', command=<recipe>)\n"
        "3. If found in flatpak (Tier 2), install via packages(action='install', method='flatpak')\n"
        "4. If found in brew (Tier 3), install via packages(action='install', method='brew')\n"
        "5. If not found, consider manage_distrobox(action='create')\n"
        "6. rpm-ostree is the absolute last resort\n\n"
        "Always explain which tier you chose and why."
    )


@mcp.prompt()
def setup_dev_environment(language: str) -> str:
    """Set up a development environment using distrobox."""
    return (
        f"Set up a {language} development environment:\n\n"
        "1. Create a distrobox with manage_distrobox(action='create', name=<name>, image=<distro>)\n"
        "2. Use manage_distrobox(action='exec', name=<name>, command=<install cmd>) to install the toolchain\n"
        "3. Use manage_distrobox(action='export', name=<name>, app=<gui-tool>) to export GUI tools\n"
        "4. Explain how to enter the container for interactive work\n\n"
        "This keeps the immutable host clean while giving full package access."
    )


@mcp.prompt()
def diagnose_service(service_name: str) -> str:
    """Debug a failing or misbehaving systemd service."""
    return (
        f"Diagnose the systemd service '{service_name}':\n\n"
        "1. Run manage_service(action='status', name='{service_name}')\n"
        "2. Use bash: journalctl -u {service_name} -n 50 to see recent logs\n"
        "3. Run manage_service(action='list', state='enabled') to check if enabled\n"
        "4. Use bash: journalctl -p err -n 20 if failed\n"
        "5. Search bazzite docs with docs(action='search', query=<topic>)\n\n"
        "Provide diagnosis and recommended fix."
    )


@mcp.prompt()
def optimize_game(game_name: str) -> str:
    """Optimize a game's settings based on hardware and community data."""
    return (
        f"Optimize '{game_name}' for this system:\n\n"
        "1. Run gaming(action='library', name_filter=<game>) to find the app ID\n"
        "2. Run system_info(detail='full') to get GPU, CPU, and RAM details\n"
        "3. Run gaming(action='reports', app_id=<id>) for ProtonDB community data\n"
        "4. Based on hardware + community reports, determine:\n"
        "   - Best Proton version to use\n"
        "   - Gamescope launch flags (resolution, scaler, FPS limit)\n"
        "   - MangoHud monitoring settings\n"
        "   - Whether to enable GameMode\n"
        "5. Apply settings with gaming(action='settings_set', app_id=<id>, ...)\n"
        "6. Enable GameMode if recommended: manage_service(name='gamemoded', action='enable', user=True)\n\n"
        "Explain each recommendation and why it suits this hardware."
    )
