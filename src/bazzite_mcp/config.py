"""Persistent configuration for bazzite-mcp."""

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]


def _config_path() -> Path:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_home / "bazzite-mcp" / "config.toml"


@dataclass
class Config:
    # GitHub
    repo_slug: str = "rolandmarg/bazzite-mcp"
    repo_local: str = ""

    # Docs cache
    cache_ttl_days: int = 7
    docs_base_url: str = "https://docs.bazzite.gg"
    github_releases_url: str = "https://api.github.com/repos/ublue-os/bazzite/releases"
    crawl_max_pages: int = 100

    # Audit
    audit_output_max_chars: int = 500

    def __post_init__(self) -> None:
        if not self.repo_local:
            self.repo_local = str(Path(__file__).resolve().parents[2])


_config: Config | None = None


def load_config() -> Config:
    global _config
    if _config is not None:
        return _config

    cfg = Config()
    path = _config_path()

    # Env vars override config file
    env_overrides = {
        "BAZZITE_MCP_REPO": "repo_slug",
        "BAZZITE_MCP_LOCAL": "repo_local",
        "BAZZITE_MCP_CACHE_TTL": "cache_ttl_days",
        "BAZZITE_MCP_CRAWL_MAX": "crawl_max_pages",
    }

    if path.exists():
        with open(path, "rb") as f:
            data = tomllib.load(f)
        for key, value in data.items():
            if hasattr(cfg, key):
                setattr(cfg, key, value)

    for env_key, attr in env_overrides.items():
        val = os.environ.get(env_key)
        if val is not None:
            field_type = type(getattr(cfg, attr))
            setattr(cfg, attr, field_type(val))

    _config = cfg
    return cfg


def reset_config() -> None:
    """Reset cached config (for testing)."""
    global _config
    _config = None
