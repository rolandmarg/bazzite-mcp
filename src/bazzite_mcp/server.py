from fastmcp import FastMCP

from bazzite_mcp.resources import (
    get_docs_index,
    get_install_hierarchy,
    get_install_policy_resource,
    get_server_info,
    get_system_overview,
)
from bazzite_mcp.tools.audit_tools import audit_log_query, rollback_action
from bazzite_mcp.tools.containers import (
    create_distrobox,
    exec_in_distrobox,
    export_distrobox_app,
    list_distroboxes,
    manage_distrobox,
    manage_podman,
    manage_quadlet,
    manage_waydroid,
)
from bazzite_mcp.tools.desktop import (
    activate_window,
    inspect_window,
    interact,
    list_windows,
    screenshot,
    screenshot_window,
    send_key,
    send_keys,
    send_mouse,
    set_text,
)
from bazzite_mcp.tools.docs import (
    bazzite_changelog,
    install_policy,
    query_bazzite_docs,
    refresh_docs_cache,
)
from bazzite_mcp.tools.gaming import game_reports, game_settings, steam_library
from bazzite_mcp.tools.packages import (
    install_package,
    list_packages,
    remove_package,
    search_package,
    update_packages,
)
from bazzite_mcp.tools.services import (
    list_services,
    manage_connection,
    manage_firewall,
    manage_service,
    manage_tailscale,
    network_status,
    service_status,
)
from bazzite_mcp.tools.settings import (
    get_display_config,
    get_settings,
    set_audio_output,
    set_display_config,
    set_power_profile,
    set_settings,
    set_theme,
)
from bazzite_mcp.tools.system import (
    disk_usage,
    hardware_info,
    journal_logs,
    process_list,
    system_info,
    update_status,
)
from bazzite_mcp.tools.ujust import ujust_list, ujust_run, ujust_show


mcp = FastMCP(
    "bazzite",
    instructions=(
        "Bazzite OS management server. Key principles:\n"
        "1. Always check ujust first for system operations (ujust_list, ujust_show, ujust_run)\n"
        "2. Follow the 6-tier install hierarchy: ujust > flatpak > brew > distrobox > AppImage > rpm-ostree\n"
        "3. Use query_bazzite_docs to search cached documentation\n"
        "4. Every mutation is audit-logged with rollback support — check audit_log_query to review actions\n"
        "5. For containers: prefer distrobox for dev environments, quadlet for persistent services\n"
        "6. rpm-ostree install is a LAST RESORT — it can freeze updates and block rebasing\n"
        "7. For gaming: use steam_library to find games, game_reports for community optimization data, "
        "game_settings to apply MangoHud/launch options. Use hardware_info + game_reports to make "
        "hardware-aware recommendations. Existing manage_service covers GameMode."
    ),
)

# ujust (Tier 1)
mcp.tool(ujust_run)
mcp.tool(ujust_list)
mcp.tool(ujust_show)

# Package management
mcp.tool(install_package)
mcp.tool(remove_package)
mcp.tool(search_package)
mcp.tool(list_packages)
mcp.tool(update_packages)

# System settings
mcp.tool(set_theme)
mcp.tool(set_audio_output)
mcp.tool(get_display_config)
mcp.tool(set_display_config)
mcp.tool(set_power_profile)
mcp.tool(get_settings)
mcp.tool(set_settings)
mcp.tool(screenshot)
mcp.tool(screenshot_window)
mcp.tool(list_windows)
mcp.tool(activate_window)
mcp.tool(inspect_window)
mcp.tool(interact)
mcp.tool(set_text)
mcp.tool(send_keys)
mcp.tool(send_key)
mcp.tool(send_mouse)

# Services and networking
mcp.tool(manage_service)
mcp.tool(service_status)
mcp.tool(list_services)
mcp.tool(network_status)
mcp.tool(manage_connection)
mcp.tool(manage_firewall)
mcp.tool(manage_tailscale)

# Containers
mcp.tool(create_distrobox)
mcp.tool(manage_distrobox)
mcp.tool(list_distroboxes)
mcp.tool(exec_in_distrobox)
mcp.tool(export_distrobox_app)
mcp.tool(manage_quadlet)
mcp.tool(manage_podman)
mcp.tool(manage_waydroid)

# System info
mcp.tool(system_info)
mcp.tool(disk_usage)
mcp.tool(update_status)
mcp.tool(journal_logs)
mcp.tool(hardware_info)
mcp.tool(process_list)

# Knowledge and docs
mcp.tool(query_bazzite_docs)
mcp.tool(bazzite_changelog)
mcp.tool(install_policy)
mcp.tool(refresh_docs_cache)

# Audit
mcp.tool(audit_log_query)
mcp.tool(rollback_action)

# Gaming
mcp.tool(steam_library)
mcp.tool(game_reports)
mcp.tool(game_settings)

# MCP Resources — read-only context
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


# MCP Prompts — reusable workflow templates
@mcp.prompt()
def troubleshoot_system(symptom: str) -> str:
    """Gather diagnostics for a system issue. Collects logs, hardware info, and service status."""
    return (
        f"The user is experiencing: {symptom}\n\n"
        "Diagnostic steps:\n"
        "1. Run system_info to get OS/kernel/desktop\n"
        "2. Run journal_logs with relevant unit or priority='err' to find errors\n"
        "3. Run hardware_info if it might be hardware-related\n"
        "4. Run service_status for relevant services\n"
        "5. Search docs with query_bazzite_docs or semantic_search_docs\n"
        "6. Check update_status for pending OS updates\n\n"
        "Provide a summary of findings and recommended fixes."
    )


@mcp.prompt()
def install_app(app_name: str) -> str:
    """Walk through the 6-tier install hierarchy to find and install an app."""
    return (
        f"Install '{app_name}' following Bazzite's 6-tier hierarchy:\n\n"
        "1. First, run search_package to check ujust, flatpak, and brew\n"
        "2. If found in ujust (Tier 1), use ujust_run\n"
        "3. If found in flatpak (Tier 2), install via install_package with method='flatpak'\n"
        "4. If found in brew (Tier 3), install via install_package with method='brew'\n"
        "5. If not found, consider creating a distrobox container\n"
        "6. rpm-ostree is the absolute last resort\n\n"
        "Always explain which tier you chose and why."
    )


@mcp.prompt()
def setup_dev_environment(language: str) -> str:
    """Set up a development environment using distrobox."""
    return (
        f"Set up a {language} development environment:\n\n"
        "1. Create a distrobox with create_distrobox (ubuntu or fedora image)\n"
        "2. Use exec_in_distrobox to install the language toolchain\n"
        "3. Use export_distrobox_app to export any GUI tools to the host menu\n"
        "4. Explain how to enter the container for interactive work\n\n"
        "This keeps the immutable host clean while giving full package access."
    )


@mcp.prompt()
def diagnose_service(service_name: str) -> str:
    """Debug a failing or misbehaving systemd service."""
    return (
        f"Diagnose the systemd service '{service_name}':\n\n"
        "1. Run service_status to see current state\n"
        "2. Run journal_logs with unit='{service_name}' to see recent logs\n"
        "3. Check if the service is enabled with list_services(state='enabled')\n"
        "4. If failed, check journal_logs with priority='err'\n"
        "5. Search bazzite docs for known issues with this service\n\n"
        "Provide diagnosis and recommended fix."
    )


@mcp.prompt()
def optimize_game(game_name: str) -> str:
    """Optimize a game's settings based on hardware and community data."""
    return (
        f"Optimize '{game_name}' for this system:\n\n"
        "1. Run steam_library to find the game and get its app ID\n"
        "2. Run hardware_info to get GPU, CPU, and RAM details\n"
        "3. Run game_reports with the app ID to get ProtonDB community data\n"
        "4. Based on hardware + community reports, determine:\n"
        "   - Best Proton version to use\n"
        "   - Gamescope launch flags (resolution, scaler, FPS limit)\n"
        "   - MangoHud monitoring settings\n"
        "   - Whether to enable GameMode\n"
        "5. Apply settings with game_settings tool\n"
        "6. Enable GameMode if recommended: manage_service(name='gamemoded', action='enable', user=True)\n\n"
        "Explain each recommendation and why it suits this hardware."
    )
