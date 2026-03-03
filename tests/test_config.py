import os

from bazzite_mcp.config import Config, load_config, reset_config


def test_config_defaults():
    cfg = Config()
    assert cfg.cache_ttl_days == 7
    assert cfg.crawl_max_pages == 100
    assert "bazzite" in cfg.docs_base_url


def test_config_env_override(monkeypatch):
    reset_config()
    monkeypatch.setenv("BAZZITE_MCP_CACHE_TTL", "14")
    cfg = load_config()
    assert cfg.cache_ttl_days == 14
    reset_config()
