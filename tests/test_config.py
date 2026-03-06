import os

import pytest

from bazzite_mcp.config import Config, load_config, reset_config


def test_config_defaults():
    cfg = Config()
    assert cfg.docs_base_url == "https://docs.bazzite.gg"
    assert "github.com/ublue-os/bazzite/releases" in cfg.github_releases_url
    assert cfg.audit_output_max_chars == 2000


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


def test_config_validation_rejects_empty_docs_base_url():
    with pytest.raises(ValueError, match="docs_base_url"):
        Config(docs_base_url="")


def test_load_config_raises_on_malformed_toml(tmp_path, monkeypatch):
    reset_config()
    config_home = tmp_path / ".config"
    cfg_dir = config_home / "bazzite-mcp"
    cfg_dir.mkdir(parents=True)
    cfg_file = cfg_dir / "config.toml"
    cfg_file.write_text("docs_base_url = ", encoding="utf-8")

    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))

    with pytest.raises(ValueError, match="Invalid TOML"):
        load_config()
    reset_config()
