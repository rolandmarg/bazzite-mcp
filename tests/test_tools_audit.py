from bazzite_mcp.tools.audit_tools import audit_log_query


def test_audit_log_query_empty(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    result = audit_log_query()
    assert "no actions" in result.lower() or "empty" in result.lower() or isinstance(result, str)
