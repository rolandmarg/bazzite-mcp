import os

import pytest

from bazzite_mcp.config import Config, load_config, reset_config


def test_config_defaults():
    cfg = Config()
    assert cfg.cache_ttl_hours == 12
    assert cfg.cache_ttl_days == 7
    assert cfg.crawl_max_pages == 100
    assert "bazzite" in cfg.docs_base_url


def test_config_env_override(monkeypatch):
    reset_config()
    monkeypatch.setenv("BAZZITE_MCP_CACHE_TTL_HOURS", "14")
    cfg = load_config()
    assert cfg.cache_ttl_hours == 14
    reset_config()


def test_loads_env_file_when_present(tmp_path, monkeypatch):
    reset_config()
    config_home = tmp_path / ".config"
    env_dir = config_home / "bazzite-mcp"
    env_dir.mkdir(parents=True)
    env_file = env_dir / "env"
    env_file.write_text("GEMINI_API_KEY=test-key\n", encoding="utf-8")

    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    _ = load_config()
    assert os.environ.get("GEMINI_API_KEY") == "test-key"
    reset_config()


def test_config_validation_rejects_negative_ttl_days():
    with pytest.raises(ValueError, match="cache_ttl_days"):
        Config(cache_ttl_days=-1)



def test_config_validation_rejects_nonpositive_crawl_pages():
    with pytest.raises(ValueError, match="crawl_max_pages"):
        Config(crawl_max_pages=0)


def test_load_config_raises_on_malformed_toml(tmp_path, monkeypatch):
    reset_config()
    config_home = tmp_path / ".config"
    cfg_dir = config_home / "bazzite-mcp"
    cfg_dir.mkdir(parents=True)
    cfg_file = cfg_dir / "config.toml"
    cfg_file.write_text("cache_ttl_hours = ", encoding="utf-8")

    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))

    with pytest.raises(ValueError, match="Invalid TOML"):
        load_config()
    reset_config()
