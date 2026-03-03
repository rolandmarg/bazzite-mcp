from bazzite_mcp.audit import AuditLog


def test_log_and_query(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    log = AuditLog()
    log.record(
        tool="install_package",
        command="flatpak install flathub org.mozilla.firefox",
        args='{"package": "firefox", "method": "flatpak"}',
        result="success",
        output="firefox installed",
        rollback="flatpak uninstall org.mozilla.firefox",
    )
    entries = log.query()
    assert len(entries) == 1
    assert entries[0]["tool"] == "install_package"
    assert entries[0]["rollback"] == "flatpak uninstall org.mozilla.firefox"


def test_query_by_tool(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    log = AuditLog()
    log.record(tool="install_package", command="brew install fd", result="success")
    log.record(tool="set_theme", command="gsettings set ...", result="success")
    entries = log.query(tool="install_package")
    assert len(entries) == 1
    assert entries[0]["tool"] == "install_package"
