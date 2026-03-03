from fastmcp import FastMCP

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
from bazzite_mcp.tools.docs import (
    bazzite_changelog,
    install_policy,
    query_bazzite_docs,
    refresh_docs_cache,
)
from bazzite_mcp.tools.packages import (
    install_package,
    list_packages,
    remove_package,
    search_package,
    update_packages,
)
from bazzite_mcp.tools.self_improve import (
    contribute_fix,
    get_server_source,
    list_improvements,
    list_pending_prs,
    suggest_improvement,
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


mcp = FastMCP("bazzite")

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

# Self-improvement
mcp.tool(suggest_improvement)
mcp.tool(contribute_fix)
mcp.tool(list_improvements)
mcp.tool(list_pending_prs)
mcp.tool(get_server_source)
