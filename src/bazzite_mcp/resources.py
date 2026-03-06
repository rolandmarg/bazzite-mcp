"""MCP resources — read-only context for AI agents."""

from bazzite_mcp import __version__
from bazzite_mcp.config import load_config
from bazzite_mcp.tools.core.docs import (
    knowledge_index_markdown,
    knowledge_resource_markdown,
)
from bazzite_mcp.tools.system import _system_info_basic


def get_system_overview() -> str:
    """Current system info snapshot."""
    return _system_info_basic()


def get_knowledge_index() -> str:
    """Index of built-in Bazzite knowledge resources and official sources."""
    return knowledge_index_markdown()


def get_install_policy() -> str:
    return knowledge_resource_markdown("install-policy")


def get_tool_routing() -> str:
    return knowledge_resource_markdown("tool-routing")


def get_troubleshooting() -> str:
    return knowledge_resource_markdown("troubleshooting")


def get_dev_environments() -> str:
    return knowledge_resource_markdown("dev-environments")


def get_game_optimization() -> str:
    return knowledge_resource_markdown("game-optimization")


def get_server_info() -> str:
    """bazzite-mcp server metadata."""
    cfg = load_config()
    return (
        f"# bazzite-mcp v{__version__}\n\n"
        f"Docs mode: lightweight knowledge resources\n"
        f"Official docs: {cfg.docs_base_url}\n"
        f"Official releases: {cfg.github_releases_url}\n"
    )
