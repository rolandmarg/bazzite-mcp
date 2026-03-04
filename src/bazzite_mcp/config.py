"""Persistent configuration for bazzite-mcp."""

import os
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]


def _config_path() -> Path:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_home / "bazzite-mcp" / "config.toml"


def _env_file_path() -> Path:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    default = config_home / "bazzite-mcp" / "env"
    return Path(os.environ.get("BAZZITE_MCP_ENV_FILE", str(default))).expanduser()


def _load_env_file() -> None:
    """Load key/value pairs from env file into process env.

    Existing environment variables always win.
    """
    path = _env_file_path()
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass
class Config:
    # GitHub
    repo_slug: str = "rolandmarg/bazzite-mcp"
    repo_local: str = ""

    # Docs cache
    cache_ttl_days: int = 7
    cache_ttl_hours: int | None = 12
    docs_base_url: str = "https://docs.bazzite.gg"
    github_releases_url: str = "https://api.github.com/repos/ublue-os/bazzite/releases"
    crawl_max_pages: int = 100

    # Embeddings (provider: "gemini" or "openai")
    embedding_provider: str = "gemini"
    embedding_model: str = "gemini-embedding-001"
    embedding_api_key_env: str = "GEMINI_API_KEY"
    embedding_dimensions: int = 768
    embedding_chunk_size: int = 2000

    # Audit
    audit_output_max_chars: int = 500

    def __post_init__(self) -> None:
        if not self.repo_local:
            self.repo_local = str(Path(__file__).resolve().parents[2])

    def cache_ttl_seconds(self) -> int:
        if self.cache_ttl_hours is not None and self.cache_ttl_hours > 0:
            return self.cache_ttl_hours * 3600
        return self.cache_ttl_days * 24 * 3600


_config: Config | None = None


def load_config() -> Config:
    _load_env_file()

    global _config
    if _config is not None:
        return _config

    cfg = Config()
    path = _config_path()

    # Env vars override config file
    env_overrides = {
        "BAZZITE_MCP_REPO": "repo_slug",
        "BAZZITE_MCP_LOCAL": "repo_local",
        "BAZZITE_MCP_CACHE_TTL_HOURS": "cache_ttl_hours",
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
