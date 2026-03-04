from unittest.mock import MagicMock

from bazzite_mcp import __version__
from bazzite_mcp import __main__ as main_module


def test_main_runs_stdio_server(monkeypatch) -> None:
    run_mock = MagicMock()
    signal_mock = MagicMock()
    register_mock = MagicMock()

    monkeypatch.setattr(main_module.mcp, "run", run_mock)
    monkeypatch.setattr(main_module.signal, "signal", signal_mock)
    monkeypatch.setattr(main_module.atexit, "register", register_mock)
    monkeypatch.setattr(main_module.sys, "argv", ["bazzite-mcp"])

    main_module.main()

    run_mock.assert_called_once_with(transport="stdio")
    assert signal_mock.call_count == 2
    register_mock.assert_called_once()


def test_main_prints_version_without_starting_server(monkeypatch, capsys) -> None:
    run_mock = MagicMock()
    monkeypatch.setattr(main_module.mcp, "run", run_mock)
    monkeypatch.setattr(main_module.sys, "argv", ["bazzite-mcp", "--version"])

    main_module.main()

    captured = capsys.readouterr()
    assert captured.out.strip() == __version__
    run_mock.assert_not_called()
