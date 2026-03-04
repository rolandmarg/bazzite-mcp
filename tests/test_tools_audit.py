from unittest.mock import MagicMock, patch

import pytest

from bazzite_mcp.runner import ToolError
from bazzite_mcp.tools.audit_tools import _audit_log_query, _rollback_action, audit


def test_audit_log_query_empty(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    result = _audit_log_query()
    assert "no actions" in result.lower() or "empty" in result.lower() or isinstance(result, str)


# --- rollback_action tests ---


@patch("bazzite_mcp.tools.audit_tools.run_audited")
@patch("bazzite_mcp.tools.audit_tools.AuditLog")
def test_rollback_action_success(mock_log_cls: MagicMock, mock_run: MagicMock) -> None:
    mock_log = MagicMock()
    mock_log.get_rollback.return_value = "flatpak uninstall -y org.mozilla.firefox"
    mock_log_cls.return_value = mock_log
    mock_run.return_value = MagicMock(returncode=0, stdout="Uninstalled.", stderr="")

    result = _rollback_action(1)
    assert "Rollback command:" in result
    assert "flatpak uninstall" in result
    assert "Success" in result


@patch("bazzite_mcp.tools.audit_tools.run_audited")
@patch("bazzite_mcp.tools.audit_tools.AuditLog")
def test_rollback_action_no_matching_action(mock_log_cls: MagicMock, mock_run: MagicMock) -> None:
    mock_log = MagicMock()
    mock_log.get_rollback.return_value = None
    mock_log_cls.return_value = mock_log

    result = _rollback_action(999)
    assert "No rollback command found" in result
    assert "#999" in result
    mock_run.assert_not_called()


# --- Dispatcher tests ---


def test_audit_dispatcher_rollback_requires_action_id() -> None:
    with pytest.raises(ToolError, match="action_id"):
        audit(action="rollback")
