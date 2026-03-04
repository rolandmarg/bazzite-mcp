"""Persistent configuration for bazzite-mcp."""

import os
import logging
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]


logger = logging.getLogger(__name__)


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
        logger.debug("No env file found at %s", path)
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
            logger.debug("Loaded env var %s from %s", key, path)


@dataclass
class Config:
    # Docs cache
    cache_ttl_days: int = 7
    cache_ttl_hours: int | None = 12
    docs_base_url: str = "https://docs.bazzite.gg"
    github_releases_url: str = "https://api.github.com/repos/ublue-os/bazzite/releases"
    crawl_max_pages: int = 100

    # Audit
    audit_output_max_chars: int = 500

    def validate(self) -> None:
        if self.cache_ttl_days < 0:
            raise ValueError("cache_ttl_days must be non-negative")
        if self.cache_ttl_hours is not None and self.cache_ttl_hours < 0:
            raise ValueError("cache_ttl_hours must be non-negative")
        if self.crawl_max_pages < 1:
            raise ValueError("crawl_max_pages must be positive")

    def __post_init__(self) -> None:
        self.validate()

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
        "BAZZITE_MCP_CACHE_TTL_HOURS": "cache_ttl_hours",
        "BAZZITE_MCP_CACHE_TTL": "cache_ttl_days",
        "BAZZITE_MCP_CRAWL_MAX": "crawl_max_pages",
    }

    if path.exists():
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except tomllib.TOMLDecodeError as exc:
            logger.error("Invalid TOML in %s: %s", path, exc)
            raise ValueError(f"Invalid TOML in {path}: {exc}") from exc
        for key, value in data.items():
            if hasattr(cfg, key):
                setattr(cfg, key, value)

    for env_key, attr in env_overrides.items():
        val = os.environ.get(env_key)
        if val is not None:
            field_type = type(getattr(cfg, attr))
            try:
                setattr(cfg, attr, field_type(val))
            except (ValueError, TypeError):
                pass  # Ignore invalid env var values, keep default

    cfg.validate()
    logger.debug(
        "Loaded bazzite-mcp config: crawl_max=%s",
        cfg.crawl_max_pages,
    )

    _config = cfg
    return cfg


def reset_config() -> None:
    """Reset cached config (for testing)."""
    global _config
    _config = None
