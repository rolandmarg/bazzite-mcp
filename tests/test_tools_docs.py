from bazzite_mcp.tools.docs import install_policy


def test_install_policy_gui_app() -> None:
    result = install_policy("gui")
    assert "flatpak" in result.lower()


def test_install_policy_cli_tool() -> None:
    result = install_policy("cli")
    assert "brew" in result.lower() or "homebrew" in result.lower()
