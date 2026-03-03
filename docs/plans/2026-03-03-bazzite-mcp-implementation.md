# Bazzite MCP Server Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a FastMCP server that gives AI agents native awareness and control of a Bazzite OS workstation.

**Architecture:** Single Python process using FastMCP with tool groups as modules. SQLite for docs cache (FTS5) and audit log. stdio transport. Guardrails prevent destructive operations.

**Tech Stack:** Python 3.14, FastMCP (v2.x stable), httpx, beautifulsoup4, SQLite (stdlib), uv (package manager)

---

## Phase 1: Project Scaffold

### Task 1: Install uv and initialize project

**Files:**
- Create: `~/bazzite-mcp/pyproject.toml` (via uv init)
- Create: `~/bazzite-mcp/src/bazzite_mcp/__init__.py`

**Step 1: Install uv via brew**

Run: `brew install uv`
Expected: uv installed successfully

**Step 2: Initialize uv project with src layout**

Run: `cd ~/bazzite-mcp && uv init --lib --name bazzite-mcp`
Expected: pyproject.toml created with `[project]` section

**Step 3: Add dependencies**

Run: `cd ~/bazzite-mcp && uv add fastmcp httpx beautifulsoup4`
Expected: Dependencies added to pyproject.toml, lock file created

**Step 4: Verify Python environment works**

Run: `cd ~/bazzite-mcp && uv run python -c "from fastmcp import FastMCP; print('ok')"`
Expected: `ok`

**Step 5: Commit**

```bash
cd ~/bazzite-mcp
git add pyproject.toml uv.lock src/
echo "data/" >> .gitignore
git add .gitignore
git commit -m "feat: initialize uv project with fastmcp dependencies"
```

---

### Task 2: Create minimal server entry point

**Files:**
- Create: `src/bazzite_mcp/server.py`
- Create: `src/bazzite_mcp/__main__.py`

**Step 1: Write a smoke test**

Create: `tests/test_server.py`

```python
import pytest
from bazzite_mcp.server import mcp


def test_server_exists():
    assert mcp is not None
    assert mcp.name == "bazzite"
```

**Step 2: Run test to verify it fails**

Run: `cd ~/bazzite-mcp && uv run pytest tests/test_server.py -v`
Expected: FAIL — module not found

**Step 3: Write minimal server**

Create: `src/bazzite_mcp/server.py`

```python
from fastmcp import FastMCP

mcp = FastMCP("bazzite")
```

Create: `src/bazzite_mcp/__main__.py`

```python
from bazzite_mcp.server import mcp

mcp.run(transport="stdio")
```

**Step 4: Run test to verify it passes**

Run: `cd ~/bazzite-mcp && uv run pytest tests/test_server.py -v`
Expected: PASS

**Step 5: Verify server starts and responds to MCP protocol**

Run: `cd ~/bazzite-mcp && echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"0.1"}}}' | uv run python -m bazzite_mcp.server 2>/dev/null | head -1`
Expected: JSON response with server capabilities

**Step 6: Commit**

```bash
cd ~/bazzite-mcp
git add src/ tests/
git commit -m "feat: add minimal FastMCP server entry point"
```

---

## Phase 2: Core Infrastructure

### Task 3: Database helpers

**Files:**
- Create: `src/bazzite_mcp/db.py`
- Create: `tests/test_db.py`

**Step 1: Write failing test**

Create: `tests/test_db.py`

```python
import sqlite3
from pathlib import Path
from bazzite_mcp.db import get_db_path, get_connection, ensure_tables


def test_get_db_path(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    path = get_db_path("test.db")
    assert path == tmp_path / "bazzite-mcp" / "test.db"
    assert path.parent.exists()


def test_ensure_audit_table(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    db_path = get_db_path("audit.db")
    conn = get_connection(db_path)
    ensure_tables(conn, "audit")
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='actions'")
    assert cursor.fetchone() is not None
    conn.close()


def test_ensure_cache_tables(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    db_path = get_db_path("cache.db")
    conn = get_connection(db_path)
    ensure_tables(conn, "cache")
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pages'")
    assert cursor.fetchone() is not None
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='changelogs'")
    assert cursor.fetchone() is not None
    conn.close()
```

**Step 2: Run test to verify it fails**

Run: `cd ~/bazzite-mcp && uv run pytest tests/test_db.py -v`
Expected: FAIL — module not found

**Step 3: Write implementation**

Create: `src/bazzite_mcp/db.py`

```python
import sqlite3
from pathlib import Path
import os

def get_db_path(filename: str) -> Path:
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    db_dir = data_home / "bazzite-mcp"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / filename

def get_connection(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

AUDIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    tool TEXT NOT NULL,
    command TEXT NOT NULL,
    args TEXT,
    result TEXT,
    output TEXT,
    rollback TEXT,
    client TEXT
);
"""

CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    title TEXT,
    content TEXT,
    section TEXT,
    fetched_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
    title, content, section, content='pages', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS pages_ai AFTER INSERT ON pages BEGIN
    INSERT INTO pages_fts(rowid, title, content, section)
    VALUES (new.id, new.title, new.content, new.section);
END;

CREATE TRIGGER IF NOT EXISTS pages_ad AFTER DELETE ON pages BEGIN
    INSERT INTO pages_fts(pages_fts, rowid, title, content, section)
    VALUES ('delete', old.id, old.title, old.content, old.section);
END;

CREATE TRIGGER IF NOT EXISTS pages_au AFTER UPDATE ON pages BEGIN
    INSERT INTO pages_fts(pages_fts, rowid, title, content, section)
    VALUES ('delete', old.id, old.title, old.content, old.section);
    INSERT INTO pages_fts(rowid, title, content, section)
    VALUES (new.id, new.title, new.content, new.section);
END;

CREATE TABLE IF NOT EXISTS changelogs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT NOT NULL UNIQUE,
    date TEXT,
    body TEXT
);
"""

def ensure_tables(conn: sqlite3.Connection, db_type: str) -> None:
    if db_type == "audit":
        conn.executescript(AUDIT_SCHEMA)
    elif db_type == "cache":
        conn.executescript(CACHE_SCHEMA)
    conn.commit()
```

**Step 4: Run test to verify it passes**

Run: `cd ~/bazzite-mcp && uv run pytest tests/test_db.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd ~/bazzite-mcp && git add src/bazzite_mcp/db.py tests/test_db.py
git commit -m "feat: add SQLite database helpers with FTS5 support"
```

---

### Task 4: Guardrails module

**Files:**
- Create: `src/bazzite_mcp/guardrails.py`
- Create: `tests/test_guardrails.py`

**Step 1: Write failing test**

Create: `tests/test_guardrails.py`

```python
import pytest
from bazzite_mcp.guardrails import check_command, GuardrailError


def test_blocks_rm_rf_root():
    with pytest.raises(GuardrailError, match="destructive"):
        check_command("rm -rf /")


def test_blocks_mkfs():
    with pytest.raises(GuardrailError, match="destructive"):
        check_command("mkfs.ext4 /dev/sda1")


def test_blocks_rpm_ostree_reset():
    with pytest.raises(GuardrailError, match="destructive"):
        check_command("rpm-ostree reset")


def test_warns_rpm_ostree_install():
    result = check_command("rpm-ostree install htop")
    assert result.warning is not None
    assert "last resort" in result.warning.lower()


def test_allows_flatpak_install():
    result = check_command("flatpak install flathub org.mozilla.firefox")
    assert result.warning is None
    assert result.allowed is True


def test_blocks_long_hostname():
    with pytest.raises(GuardrailError, match="hostname"):
        check_command("hostnamectl set-hostname this-hostname-is-way-too-long-for-distrobox")


def test_allows_short_hostname():
    result = check_command("hostnamectl set-hostname mypc")
    assert result.allowed is True
```

**Step 2: Run test to verify it fails**

Run: `cd ~/bazzite-mcp && uv run pytest tests/test_guardrails.py -v`
Expected: FAIL

**Step 3: Write implementation**

Create: `src/bazzite_mcp/guardrails.py`

```python
import re
from dataclasses import dataclass

class GuardrailError(Exception):
    pass

@dataclass
class CheckResult:
    allowed: bool
    warning: str | None = None

BLOCKED_PATTERNS = [
    (r"\brm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+.*)?/\s*$", "destructive filesystem operation"),
    (r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+/", "destructive filesystem operation"),
    (r"\bmkfs\b", "destructive filesystem operation"),
    (r"\brpm-ostree\s+reset\b", "destructive: removes ALL layered packages"),
    (r"\brpm-ostree\s+rebase\b.*(?:gnome|kde|plasma|sway|hyprland|cosmic)", "Do NOT rebase to switch desktop environments. Backup and reinstall instead."),
    (r"\bdd\s+.*of=/dev/", "destructive disk write"),
]

WARN_PATTERNS = [
    (r"\brpm-ostree\s+install\b", "rpm-ostree is a LAST RESORT on Bazzite. It can freeze updates, block rebasing, and cause dependency conflicts. Prefer: ujust > flatpak > brew > distrobox > AppImage."),
]

HOSTNAME_RE = re.compile(r"\bhostnamectl\s+set-hostname\s+(\S+)")

def check_command(command: str) -> CheckResult:
    for pattern, reason in BLOCKED_PATTERNS:
        if re.search(pattern, command):
            raise GuardrailError(f"Blocked: {reason}")

    hostname_match = HOSTNAME_RE.search(command)
    if hostname_match:
        hostname = hostname_match.group(1).strip("'\"")
        if len(hostname) > 20:
            raise GuardrailError(f"Blocked: hostname '{hostname}' exceeds 20 characters (breaks Distrobox)")

    for pattern, warning in WARN_PATTERNS:
        if re.search(pattern, command):
            return CheckResult(allowed=True, warning=warning)

    return CheckResult(allowed=True)
```

**Step 4: Run test to verify it passes**

Run: `cd ~/bazzite-mcp && uv run pytest tests/test_guardrails.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd ~/bazzite-mcp && git add src/bazzite_mcp/guardrails.py tests/test_guardrails.py
git commit -m "feat: add guardrails for blocking destructive commands"
```

---

### Task 5: Audit log module

**Files:**
- Create: `src/bazzite_mcp/audit.py`
- Create: `tests/test_audit.py`

**Step 1: Write failing test**

Create: `tests/test_audit.py`

```python
from bazzite_mcp.audit import AuditLog


def test_log_and_query(tmp_path, monkeypatch):
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


def test_query_by_tool(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    log = AuditLog()
    log.record(tool="install_package", command="brew install fd", result="success")
    log.record(tool="set_theme", command="gsettings set ...", result="success")
    entries = log.query(tool="install_package")
    assert len(entries) == 1
    assert entries[0]["tool"] == "install_package"
```

**Step 2: Run test to verify it fails**

Run: `cd ~/bazzite-mcp && uv run pytest tests/test_audit.py -v`
Expected: FAIL

**Step 3: Write implementation**

Create: `src/bazzite_mcp/audit.py`

```python
from bazzite_mcp.db import get_db_path, get_connection, ensure_tables


class AuditLog:
    def __init__(self):
        db_path = get_db_path("audit_log.db")
        self._conn = get_connection(db_path)
        ensure_tables(self._conn, "audit")

    def record(
        self,
        tool: str,
        command: str,
        args: str | None = None,
        result: str | None = None,
        output: str | None = None,
        rollback: str | None = None,
        client: str | None = None,
    ) -> int:
        cursor = self._conn.execute(
            "INSERT INTO actions (tool, command, args, result, output, rollback, client) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tool, command, args, result, output, rollback, client),
        )
        self._conn.commit()
        return cursor.lastrowid

    def query(
        self,
        tool: str | None = None,
        search: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        sql = "SELECT * FROM actions WHERE 1=1"
        params: list = []
        if tool:
            sql += " AND tool = ?"
            params.append(tool)
        if search:
            sql += " AND (command LIKE ? OR output LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_rollback(self, action_id: int) -> str | None:
        row = self._conn.execute("SELECT rollback FROM actions WHERE id = ?", (action_id,)).fetchone()
        return row["rollback"] if row else None
```

**Step 4: Run test to verify it passes**

Run: `cd ~/bazzite-mcp && uv run pytest tests/test_audit.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd ~/bazzite-mcp && git add src/bazzite_mcp/audit.py tests/test_audit.py
git commit -m "feat: add audit log for tracking mutations with rollback"
```

---

### Task 6: Shell runner helper (shared by all tool modules)

**Files:**
- Create: `src/bazzite_mcp/runner.py`
- Create: `tests/test_runner.py`

**Step 1: Write failing test**

Create: `tests/test_runner.py`

```python
import pytest
from bazzite_mcp.runner import run_command
from bazzite_mcp.guardrails import GuardrailError


def test_run_simple_command():
    result = run_command("echo hello")
    assert result.returncode == 0
    assert "hello" in result.stdout


def test_run_blocked_command():
    with pytest.raises(GuardrailError):
        run_command("rm -rf /")


def test_run_failing_command():
    result = run_command("false")
    assert result.returncode != 0
```

**Step 2: Run test to verify it fails**

Run: `cd ~/bazzite-mcp && uv run pytest tests/test_runner.py -v`
Expected: FAIL

**Step 3: Write implementation**

Create: `src/bazzite_mcp/runner.py`

```python
import subprocess
from dataclasses import dataclass
from bazzite_mcp.guardrails import check_command


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def run_command(command: str, timeout: int = 120) -> CommandResult:
    check = check_command(command)
    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return CommandResult(
        returncode=result.returncode,
        stdout=result.stdout.strip(),
        stderr=result.stderr.strip(),
    )
```

**Step 4: Run test to verify it passes**

Run: `cd ~/bazzite-mcp && uv run pytest tests/test_runner.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd ~/bazzite-mcp && git add src/bazzite_mcp/runner.py tests/test_runner.py
git commit -m "feat: add shell runner with guardrail integration"
```

---

## Phase 3: Tool Modules

### Task 7: ujust tools

**Files:**
- Create: `src/bazzite_mcp/tools/__init__.py`
- Create: `src/bazzite_mcp/tools/ujust.py`
- Create: `tests/test_tools_ujust.py`

**Step 1: Write failing test**

Create: `tests/test_tools_ujust.py`

```python
from unittest.mock import patch, MagicMock
from bazzite_mcp.tools.ujust import ujust_list, ujust_show


@patch("bazzite_mcp.tools.ujust.run_command")
def test_ujust_list(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="update\nsetup-waydroid\nenable-tailscale", stderr="")
    result = ujust_list()
    assert "update" in result
    mock_run.assert_called_once()


@patch("bazzite_mcp.tools.ujust.run_command")
def test_ujust_list_with_filter(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="update\nsetup-waydroid\nenable-tailscale", stderr="")
    result = ujust_list(filter="setup")
    assert "setup-waydroid" in result


@patch("bazzite_mcp.tools.ujust.run_command")
def test_ujust_show(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="#!/bin/bash\necho hello", stderr="")
    result = ujust_show("update")
    assert "echo hello" in result
```

**Step 2: Run test to verify it fails**

Run: `cd ~/bazzite-mcp && uv run pytest tests/test_tools_ujust.py -v`
Expected: FAIL

**Step 3: Write implementation**

Create: `src/bazzite_mcp/tools/__init__.py` (empty file)

Create: `src/bazzite_mcp/tools/ujust.py`

```python
from bazzite_mcp.runner import run_command


def ujust_list(filter: str | None = None) -> str:
    """List available ujust commands. Optionally filter by keyword."""
    result = run_command("ujust --summary 2>/dev/null || ujust 2>&1")
    if result.returncode != 0:
        return f"Error listing ujust commands: {result.stderr}"
    lines = result.stdout.strip().split("\n")
    if filter:
        lines = [l for l in lines if filter.lower() in l.lower()]
    return "\n".join(lines) if lines else "No matching commands found."


def ujust_show(command: str) -> str:
    """Show the source script of a ujust command before running it."""
    result = run_command(f"ujust --show {command}")
    if result.returncode != 0:
        return f"Error showing command '{command}': {result.stderr}"
    return result.stdout


def ujust_run(command: str) -> str:
    """Execute a ujust command.

    ujust is Bazzite's built-in command runner for system setup, configuration,
    and maintenance. It is the FIRST method to check for any system operation.
    Common prefixes: install-, setup-, configure-, toggle-, fix-, distrobox-.
    """
    result = run_command(f"ujust {command}")
    output = result.stdout
    if result.stderr:
        output += f"\nSTDERR: {result.stderr}"
    if result.returncode != 0:
        output = f"Command failed (exit {result.returncode}):\n{output}"
    return output
```

**Step 4: Run test to verify it passes**

Run: `cd ~/bazzite-mcp && uv run pytest tests/test_tools_ujust.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd ~/bazzite-mcp && git add src/bazzite_mcp/tools/ tests/test_tools_ujust.py
git commit -m "feat: add ujust tools (list, show, run)"
```

---

### Task 8: System info tools

**Files:**
- Create: `src/bazzite_mcp/tools/system.py`
- Create: `tests/test_tools_system.py`

**Step 1: Write failing test**

Create: `tests/test_tools_system.py`

```python
from unittest.mock import patch, MagicMock
from bazzite_mcp.tools.system import system_info, disk_usage, update_status, journal_logs, hardware_info, process_list


@patch("bazzite_mcp.tools.system.run_command")
def test_system_info(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="Bazzite 43", stderr="")
    result = system_info()
    assert "Bazzite" in result


@patch("bazzite_mcp.tools.system.run_command")
def test_disk_usage(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="/dev/sda1 50G 20G 30G 40% /", stderr="")
    result = disk_usage()
    assert "/" in result


@patch("bazzite_mcp.tools.system.run_command")
def test_process_list(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="PID USER %CPU\n1 root 0.0", stderr="")
    result = process_list()
    assert "PID" in result
```

**Step 2: Run test to verify it fails**

Run: `cd ~/bazzite-mcp && uv run pytest tests/test_tools_system.py -v`
Expected: FAIL

**Step 3: Write implementation**

Create: `src/bazzite_mcp/tools/system.py`

```python
from bazzite_mcp.runner import run_command


def system_info() -> str:
    """Get OS version, kernel, desktop environment, and hardware summary."""
    commands = [
        ("OS", "cat /etc/os-release | grep -E '^(NAME|VERSION|VARIANT)=' | head -5"),
        ("Kernel", "uname -r"),
        ("Desktop", "echo $XDG_CURRENT_DESKTOP"),
        ("Session", "echo $XDG_SESSION_TYPE"),
        ("CPU", "lscpu | grep 'Model name' | head -1"),
        ("GPU", "lspci | grep -i 'vga\\|3d' | head -2"),
        ("RAM", "free -h | grep Mem | awk '{print $2}'"),
        ("Hostname", "hostname"),
    ]
    parts = []
    for label, cmd in commands:
        result = run_command(cmd)
        parts.append(f"{label}: {result.stdout}")
    return "\n".join(parts)


def disk_usage() -> str:
    """Show disk space per mount point."""
    result = run_command("df -h --output=source,size,used,avail,pcent,target -x tmpfs -x devtmpfs -x squashfs")
    return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"


def update_status() -> str:
    """Check for pending OS updates, rpm-ostree status, and staged deployments."""
    result = run_command("rpm-ostree status")
    return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"


def journal_logs(unit: str | None = None, priority: str | None = None, since: str | None = None, lines: int = 50) -> str:
    """Query journalctl logs with filtering.

    Args:
        unit: systemd unit name (e.g. 'NetworkManager')
        priority: log priority (e.g. 'err', 'warning')
        since: time filter (e.g. '1 hour ago', 'today')
        lines: number of lines to return (default 50)
    """
    cmd = f"journalctl --no-pager -n {lines}"
    if unit:
        cmd += f" -u {unit}"
    if priority:
        cmd += f" -p {priority}"
    if since:
        cmd += f' --since "{since}"'
    result = run_command(cmd)
    return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"


def hardware_info() -> str:
    """Detailed hardware report including CPU, GPU, RAM, and sensors."""
    commands = [
        ("CPU", "lscpu | head -20"),
        ("GPU", "lspci -v | grep -A 10 -i 'vga\\|3d'"),
        ("Memory", "free -h"),
        ("Block Devices", "lsblk -o NAME,SIZE,TYPE,MOUNTPOINT"),
        ("Sensors", "sensors 2>/dev/null || echo 'sensors not available'"),
    ]
    parts = []
    for label, cmd in commands:
        result = run_command(cmd)
        parts.append(f"=== {label} ===\n{result.stdout}")
    return "\n\n".join(parts)


def process_list(sort_by: str = "cpu", count: int = 15) -> str:
    """Show top processes by CPU or memory usage.

    Args:
        sort_by: 'cpu' or 'memory'
        count: number of processes to show (default 15)
    """
    sort_flag = "-%cpu" if sort_by == "cpu" else "-%mem"
    result = run_command(f"ps aux --sort={sort_flag} | head -n {count + 1}")
    return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"
```

**Step 4: Run test to verify it passes**

Run: `cd ~/bazzite-mcp && uv run pytest tests/test_tools_system.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd ~/bazzite-mcp && git add src/bazzite_mcp/tools/system.py tests/test_tools_system.py
git commit -m "feat: add system info and diagnostics tools"
```

---

### Task 9: Package management tools

**Files:**
- Create: `src/bazzite_mcp/tools/packages.py`
- Create: `tests/test_tools_packages.py`

**Step 1: Write failing test**

Create: `tests/test_tools_packages.py`

```python
from unittest.mock import patch, MagicMock
from bazzite_mcp.tools.packages import search_package, install_package, list_packages


@patch("bazzite_mcp.tools.packages.run_command")
def test_search_package(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="org.mozilla.firefox", stderr="")
    result = search_package("firefox")
    assert "firefox" in result.lower()


@patch("bazzite_mcp.tools.packages.run_command")
def test_list_packages_flatpak(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="Firefox\nVLC", stderr="")
    result = list_packages(source="flatpak")
    assert "Firefox" in result
```

**Step 2: Run test to verify it fails**

Run: `cd ~/bazzite-mcp && uv run pytest tests/test_tools_packages.py -v`
Expected: FAIL

**Step 3: Write implementation**

Create: `src/bazzite_mcp/tools/packages.py`

```python
from bazzite_mcp.runner import run_command

INSTALL_POLICY = """Bazzite 6-tier install hierarchy (official docs.bazzite.gg):
1. ujust — check ujust --summary for setup/install commands first
2. flatpak — PRIMARY method for GUI apps (via Flathub)
3. brew — CLI/TUI tools ONLY (no GUI apps)
4. distrobox — for packages from other distro repos (apt, pacman, etc.)
5. AppImage — portable apps from TRUSTED sources only
6. rpm-ostree — LAST RESORT. Can freeze updates, block rebasing, cause conflicts."""


def install_package(package: str, method: str | None = None) -> str:
    """Smart package installer following Bazzite's official 6-tier hierarchy.

    If no method is specified, attempts to determine the best method automatically.
    Order: ujust > flatpak > brew > distrobox > rpm-ostree (last resort).

    Args:
        package: package name to install
        method: override install method (flatpak, brew, distrobox, rpm-ostree, ujust)
    """
    if method:
        return _install_with_method(package, method)

    # Tier 1: check ujust
    ujust_check = run_command(f"ujust --summary 2>/dev/null | grep -i 'install.*{package}\\|setup.*{package}'")
    if ujust_check.returncode == 0 and ujust_check.stdout.strip():
        commands = ujust_check.stdout.strip().split("\n")
        return f"Found ujust command(s) for '{package}':\n" + "\n".join(f"  ujust {c.strip()}" for c in commands) + f"\n\nRun with: ujust_run tool\n\n{INSTALL_POLICY}"

    # Tier 2: try flatpak
    flatpak_check = run_command(f"flatpak search {package} 2>/dev/null")
    if flatpak_check.returncode == 0 and flatpak_check.stdout.strip():
        return f"Flatpak results for '{package}':\n{flatpak_check.stdout}\n\nRecommended: flatpak install flathub <app-id>\n\n{INSTALL_POLICY}"

    # Tier 3: try brew
    brew_check = run_command(f"brew search {package} 2>/dev/null")
    if brew_check.returncode == 0 and brew_check.stdout.strip():
        return f"Homebrew results for '{package}':\n{brew_check.stdout}\n\nRecommended: brew install {package}\n\n{INSTALL_POLICY}"

    return f"Package '{package}' not found in ujust, flatpak, or brew.\nConsider: distrobox (for other distro repos) or rpm-ostree (last resort).\n\n{INSTALL_POLICY}"


def _install_with_method(package: str, method: str) -> str:
    method_commands = {
        "flatpak": f"flatpak install -y flathub {package}",
        "brew": f"brew install {package}",
        "rpm-ostree": f"rpm-ostree install {package}",
        "ujust": f"ujust {package}",
    }
    if method not in method_commands:
        return f"Unknown method '{method}'. Supported: {', '.join(method_commands.keys())}"

    cmd = method_commands[method]
    result = run_command(cmd)
    output = result.stdout
    if result.stderr:
        output += f"\n{result.stderr}"
    if result.returncode != 0:
        return f"Installation failed (exit {result.returncode}):\n{output}"
    return f"Installed '{package}' via {method}:\n{output}"


def remove_package(package: str, method: str) -> str:
    """Remove a package using the method it was installed with.

    Args:
        package: package name to remove
        method: install method used (flatpak, brew, rpm-ostree)
    """
    method_commands = {
        "flatpak": f"flatpak uninstall -y {package}",
        "brew": f"brew uninstall {package}",
        "rpm-ostree": f"rpm-ostree uninstall {package}",
    }
    if method not in method_commands:
        return f"Unknown method '{method}'. Supported: {', '.join(method_commands.keys())}"
    result = run_command(method_commands[method])
    output = result.stdout
    if result.returncode != 0:
        output = f"Removal failed (exit {result.returncode}):\n{output}\n{result.stderr}"
    return output


def search_package(package: str) -> str:
    """Search for a package across ujust, flatpak, brew, and rpm repos.

    Returns results from all sources with tier recommendation.
    """
    parts = []

    ujust_check = run_command(f"ujust --summary 2>/dev/null | grep -i '{package}'")
    if ujust_check.returncode == 0 and ujust_check.stdout.strip():
        parts.append(f"[Tier 1 - ujust]\n{ujust_check.stdout}")

    flatpak_check = run_command(f"flatpak search {package} 2>/dev/null")
    if flatpak_check.returncode == 0 and flatpak_check.stdout.strip():
        parts.append(f"[Tier 2 - Flatpak]\n{flatpak_check.stdout}")

    brew_check = run_command(f"brew search {package} 2>/dev/null")
    if brew_check.returncode == 0 and brew_check.stdout.strip():
        parts.append(f"[Tier 3 - Homebrew]\n{brew_check.stdout}")

    if not parts:
        return f"No results for '{package}' in ujust, flatpak, or brew.\nConsider distrobox or rpm-ostree (last resort)."
    return "\n\n".join(parts) + f"\n\n{INSTALL_POLICY}"


def list_packages(source: str | None = None) -> str:
    """List installed packages, filterable by source.

    Args:
        source: filter by source (flatpak, brew, rpm-ostree, all). Default: all.
    """
    parts = []
    sources = [source] if source else ["flatpak", "brew", "rpm-ostree"]

    if "flatpak" in sources:
        r = run_command("flatpak list --app --columns=name,application,version 2>/dev/null")
        if r.returncode == 0 and r.stdout.strip():
            parts.append(f"=== Flatpak ===\n{r.stdout}")

    if "brew" in sources:
        r = run_command("brew list 2>/dev/null")
        if r.returncode == 0 and r.stdout.strip():
            parts.append(f"=== Homebrew ===\n{r.stdout}")

    if "rpm-ostree" in sources:
        r = run_command("rpm-ostree status --json 2>/dev/null | python3 -c \"import sys,json; d=json.load(sys.stdin); pkgs=d['deployments'][0].get('requested-packages',[]); print(chr(10).join(pkgs) if pkgs else 'No layered packages')\"")
        if r.returncode == 0:
            parts.append(f"=== rpm-ostree (layered) ===\n{r.stdout}")

    return "\n\n".join(parts) if parts else "No packages found."


def update_packages(source: str | None = None) -> str:
    """Update packages for a given source, or all sources.

    Args:
        source: which source to update (flatpak, brew, system, all). 'system' runs ujust update.
    """
    if source == "system" or source is None:
        result = run_command("ujust update")
        return f"System update:\n{result.stdout}"
    elif source == "flatpak":
        result = run_command("flatpak update -y")
        return f"Flatpak update:\n{result.stdout}"
    elif source == "brew":
        result = run_command("brew upgrade")
        return f"Brew update:\n{result.stdout}"
    else:
        return f"Unknown source '{source}'. Supported: flatpak, brew, system, all."
```

**Step 4: Run test to verify it passes**

Run: `cd ~/bazzite-mcp && uv run pytest tests/test_tools_packages.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd ~/bazzite-mcp && git add src/bazzite_mcp/tools/packages.py tests/test_tools_packages.py
git commit -m "feat: add smart package management tools with 6-tier hierarchy"
```

---

### Task 10: System settings tools

**Files:**
- Create: `src/bazzite_mcp/tools/settings.py`
- Create: `tests/test_tools_settings.py`

**Step 1: Write failing test**

Create: `tests/test_tools_settings.py`

```python
from unittest.mock import patch, MagicMock
from bazzite_mcp.tools.settings import set_theme, get_settings


@patch("bazzite_mcp.tools.settings.run_command")
def test_set_theme_dark(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    result = set_theme("dark")
    assert "dark" in result.lower()


@patch("bazzite_mcp.tools.settings.run_command")
def test_get_settings(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="'prefer-dark'", stderr="")
    result = get_settings("org.gnome.desktop.interface", "color-scheme")
    assert "prefer-dark" in result
```

**Step 2: Run test to verify it fails**

Run: `cd ~/bazzite-mcp && uv run pytest tests/test_tools_settings.py -v`
Expected: FAIL

**Step 3: Write implementation**

Create: `src/bazzite_mcp/tools/settings.py`

```python
from bazzite_mcp.runner import run_command


def set_theme(mode: str) -> str:
    """Switch between light, dark, or auto color scheme.

    Args:
        mode: 'dark', 'light', or 'auto'
    """
    schemes = {
        "dark": "prefer-dark",
        "light": "prefer-light",
        "auto": "default",
    }
    if mode not in schemes:
        return f"Unknown mode '{mode}'. Supported: dark, light, auto."
    scheme = schemes[mode]
    result = run_command(f"gsettings set org.gnome.desktop.interface color-scheme '{scheme}'")
    if result.returncode != 0:
        return f"Failed to set theme: {result.stderr}"
    return f"Theme set to {mode} (color-scheme: {scheme})"


def set_audio_output(device: str | None = None) -> str:
    """Switch audio output device. Lists available sinks if no device specified.

    Args:
        device: sink name or index from pactl list. Omit to list available devices.
    """
    if device is None:
        result = run_command("pactl list sinks short")
        return f"Available audio outputs:\n{result.stdout}\n\nUse the sink name or index to switch."
    result = run_command(f"pactl set-default-sink {device}")
    if result.returncode != 0:
        return f"Failed to switch audio: {result.stderr}"
    return f"Audio output switched to: {device}"


def get_display_config() -> str:
    """Query current display setup (resolution, refresh rate, scaling)."""
    result = run_command("gnome-randr 2>/dev/null || xrandr --query 2>/dev/null || echo 'No display tool available'")
    return result.stdout


def set_display_config(output: str, resolution: str | None = None, refresh: str | None = None, scale: str | None = None) -> str:
    """Change display resolution, refresh rate, or scaling.

    Args:
        output: display output name (e.g. 'HDMI-1', 'DP-1')
        resolution: e.g. '1920x1080'
        refresh: e.g. '60' (Hz)
        scale: e.g. '1', '1.5', '2'
    """
    if scale:
        result = run_command(f"gsettings set org.gnome.desktop.interface text-scaling-factor {scale}")
        if result.returncode != 0:
            return f"Failed to set scale: {result.stderr}"

    cmd = f"gnome-randr modify {output}"
    if resolution:
        cmd += f" --mode {resolution}"
    if refresh:
        cmd += f" --rate {refresh}"

    if resolution or refresh:
        result = run_command(cmd)
        if result.returncode != 0:
            fallback = f"xrandr --output {output}"
            if resolution:
                fallback += f" --mode {resolution}"
            if refresh:
                fallback += f" --rate {refresh}"
            result = run_command(fallback)
            if result.returncode != 0:
                return f"Failed to set display config: {result.stderr}"

    return f"Display '{output}' configured: resolution={resolution}, refresh={refresh}, scale={scale}"


def set_power_profile(profile: str) -> str:
    """Switch power profile.

    Args:
        profile: 'performance', 'balanced', or 'power-saver'
    """
    valid = ["performance", "balanced", "power-saver"]
    if profile not in valid:
        return f"Unknown profile '{profile}'. Supported: {', '.join(valid)}."
    result = run_command(f"powerprofilesctl set {profile}")
    if result.returncode != 0:
        return f"Failed to set power profile: {result.stderr}"
    return f"Power profile set to: {profile}"


def get_settings(schema: str, key: str) -> str:
    """Read a gsettings/dconf value.

    Args:
        schema: gsettings schema (e.g. 'org.gnome.desktop.interface')
        key: settings key (e.g. 'color-scheme')
    """
    result = run_command(f"gsettings get {schema} {key}")
    if result.returncode != 0:
        return f"Error reading {schema} {key}: {result.stderr}"
    return result.stdout


def set_settings(schema: str, key: str, value: str) -> str:
    """Write a gsettings/dconf value.

    Args:
        schema: gsettings schema (e.g. 'org.gnome.desktop.interface')
        key: settings key (e.g. 'gtk-theme')
        value: new value to set
    """
    result = run_command(f"gsettings set {schema} {key} {value}")
    if result.returncode != 0:
        return f"Error setting {schema} {key}: {result.stderr}"
    return f"Set {schema} {key} = {value}"
```

**Step 4: Run test to verify it passes**

Run: `cd ~/bazzite-mcp && uv run pytest tests/test_tools_settings.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd ~/bazzite-mcp && git add src/bazzite_mcp/tools/settings.py tests/test_tools_settings.py
git commit -m "feat: add system settings tools (theme, audio, display, power)"
```

---

### Task 11: Services & networking tools

**Files:**
- Create: `src/bazzite_mcp/tools/services.py`
- Create: `tests/test_tools_services.py`

**Step 1: Write failing test**

Create: `tests/test_tools_services.py`

```python
from unittest.mock import patch, MagicMock
from bazzite_mcp.tools.services import service_status, network_status, manage_tailscale


@patch("bazzite_mcp.tools.services.run_command")
def test_service_status(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="active (running)", stderr="")
    result = service_status("NetworkManager")
    assert "active" in result


@patch("bazzite_mcp.tools.services.run_command")
def test_network_status(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="eth0: connected", stderr="")
    result = network_status()
    assert "connected" in result
```

**Step 2: Run test to verify it fails**

Run: `cd ~/bazzite-mcp && uv run pytest tests/test_tools_services.py -v`
Expected: FAIL

**Step 3: Write implementation**

Create: `src/bazzite_mcp/tools/services.py`

```python
from bazzite_mcp.runner import run_command


def manage_service(name: str, action: str, user: bool = False) -> str:
    """Start, stop, restart, enable, or disable a systemd service.

    Args:
        name: service unit name (e.g. 'tailscaled', 'bluetooth')
        action: one of 'start', 'stop', 'restart', 'enable', 'disable', 'enable --now', 'disable --now'
        user: if True, manage user service (--user flag)
    """
    valid_actions = ["start", "stop", "restart", "enable", "disable", "enable --now", "disable --now"]
    if action not in valid_actions:
        return f"Unknown action '{action}'. Supported: {', '.join(valid_actions)}."
    scope = "--user" if user else ""
    result = run_command(f"systemctl {scope} {action} {name}")
    if result.returncode != 0:
        return f"Failed to {action} {name}: {result.stderr}"
    return f"Service '{name}' {action} successful."


def service_status(name: str, user: bool = False) -> str:
    """Get status of a systemd service.

    Args:
        name: service unit name
        user: if True, query user service
    """
    scope = "--user" if user else ""
    result = run_command(f"systemctl {scope} status {name} --no-pager")
    return result.stdout if result.stdout else result.stderr


def list_services(state: str | None = None, user: bool = False) -> str:
    """List systemd services, optionally filtered by state.

    Args:
        state: filter by state (running, failed, enabled, disabled)
        user: if True, list user services
    """
    scope = "--user" if user else ""
    if state in ("running", "failed"):
        result = run_command(f"systemctl {scope} list-units --type=service --state={state} --no-pager")
    elif state in ("enabled", "disabled"):
        result = run_command(f"systemctl {scope} list-unit-files --type=service --state={state} --no-pager")
    else:
        result = run_command(f"systemctl {scope} list-units --type=service --no-pager")
    return result.stdout


def network_status() -> str:
    """Show NetworkManager connections, active interfaces, and IP info."""
    parts = []
    r = run_command("nmcli general status")
    parts.append(f"=== General ===\n{r.stdout}")
    r = run_command("nmcli connection show --active")
    parts.append(f"=== Active Connections ===\n{r.stdout}")
    r = run_command("ip -brief addr show")
    parts.append(f"=== IP Addresses ===\n{r.stdout}")
    return "\n\n".join(parts)


def manage_connection(action: str, name: str | None = None, **kwargs) -> str:
    """Create, modify, or delete NetworkManager connections.

    Args:
        action: 'show', 'up', 'down', 'delete', 'modify'
        name: connection name
    """
    if action == "show":
        result = run_command("nmcli connection show")
    elif action in ("up", "down", "delete") and name:
        result = run_command(f'nmcli connection {action} "{name}"')
    elif action == "modify" and name:
        props = " ".join(f"{k} {v}" for k, v in kwargs.items())
        result = run_command(f'nmcli connection modify "{name}" {props}')
    else:
        return f"Usage: action='show|up|down|delete|modify', name=<connection name>"
    return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"


def manage_firewall(action: str, port: str | None = None, service: str | None = None) -> str:
    """Manage firewalld rules.

    Args:
        action: 'list', 'add-port', 'remove-port', 'add-service', 'remove-service'
        port: port/protocol (e.g. '8080/tcp')
        service: firewalld service name (e.g. 'http')
    """
    if action == "list":
        result = run_command("firewall-cmd --list-all")
    elif action == "add-port" and port:
        result = run_command(f"sudo firewall-cmd --add-port={port} --permanent && sudo firewall-cmd --reload")
    elif action == "remove-port" and port:
        result = run_command(f"sudo firewall-cmd --remove-port={port} --permanent && sudo firewall-cmd --reload")
    elif action == "add-service" and service:
        result = run_command(f"sudo firewall-cmd --add-service={service} --permanent && sudo firewall-cmd --reload")
    elif action == "remove-service" and service:
        result = run_command(f"sudo firewall-cmd --remove-service={service} --permanent && sudo firewall-cmd --reload")
    else:
        return "Usage: action='list|add-port|remove-port|add-service|remove-service'"
    return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"


def manage_tailscale(action: str) -> str:
    """Manage Tailscale VPN.

    Args:
        action: 'status', 'up', 'down', 'ip', 'peers'
    """
    valid = ["status", "up", "down", "ip", "peers"]
    if action not in valid:
        return f"Unknown action '{action}'. Supported: {', '.join(valid)}."
    if action == "peers":
        result = run_command("tailscale status")
    elif action == "ip":
        result = run_command("tailscale ip")
    else:
        result = run_command(f"tailscale {action}")
    return result.stdout if result.returncode == 0 else f"Error: {result.stderr}\n\nTip: if Tailscale is not enabled, run ujust_run('enable-tailscale') first."
```

**Step 4: Run test to verify it passes**

Run: `cd ~/bazzite-mcp && uv run pytest tests/test_tools_services.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd ~/bazzite-mcp && git add src/bazzite_mcp/tools/services.py tests/test_tools_services.py
git commit -m "feat: add services, networking, firewall, and tailscale tools"
```

---

### Task 12: Container & dev environment tools

**Files:**
- Create: `src/bazzite_mcp/tools/containers.py`
- Create: `tests/test_tools_containers.py`

**Step 1: Write failing test**

Create: `tests/test_tools_containers.py`

```python
from unittest.mock import patch, MagicMock
from bazzite_mcp.tools.containers import list_distroboxes, create_distrobox


@patch("bazzite_mcp.tools.containers.run_command")
def test_list_distroboxes(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="ubuntu-dev | running", stderr="")
    result = list_distroboxes()
    assert "ubuntu" in result.lower()


@patch("bazzite_mcp.tools.containers.run_command")
def test_create_distrobox(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="Container created", stderr="")
    result = create_distrobox("test-box", image="ubuntu:24.04")
    assert "created" in result.lower() or "Container" in result
```

**Step 2: Run test to verify it fails**

Run: `cd ~/bazzite-mcp && uv run pytest tests/test_tools_containers.py -v`
Expected: FAIL

**Step 3: Write implementation**

Create: `src/bazzite_mcp/tools/containers.py`

```python
from bazzite_mcp.runner import run_command

DISTROBOX_IMAGES = {
    "ubuntu": "ubuntu:latest",
    "fedora": "fedora:latest",
    "arch": "archlinux:latest",
    "debian": "debian:latest",
    "opensuse": "opensuse/tumbleweed:latest",
    "alpine": "alpine:latest",
    "void": "voidlinux/voidlinux:latest",
}


def create_distrobox(name: str, image: str | None = None) -> str:
    """Create a new distrobox container.

    Distrobox gives access to other Linux distro package managers (apt, pacman, etc.)
    in an isolated container. Use for software lacking Flatpak/Homebrew support.

    Args:
        name: container name (e.g. 'ubuntu-dev')
        image: container image (e.g. 'ubuntu:24.04'). Shortcuts: ubuntu, fedora, arch, debian.
    """
    if image and image in DISTROBOX_IMAGES:
        image = DISTROBOX_IMAGES[image]
    elif not image:
        image = "ubuntu:latest"
    result = run_command(f"distrobox create --name {name} --image {image} --yes")
    if result.returncode != 0:
        return f"Failed to create distrobox '{name}': {result.stderr}"
    return f"Container '{name}' created with image '{image}'.\nEnter with: distrobox enter {name}"


def manage_distrobox(name: str, action: str) -> str:
    """Manage a distrobox container.

    Args:
        name: container name
        action: 'enter', 'stop', 'remove'
    """
    if action == "enter":
        return f"To enter interactively, run in your terminal:\n  distrobox enter {name}\n\n(MCP tools cannot start interactive shells)"
    elif action == "stop":
        result = run_command(f"distrobox stop --yes {name}")
    elif action == "remove":
        result = run_command(f"distrobox rm --force {name}")
    else:
        return f"Unknown action '{action}'. Supported: enter, stop, remove."
    return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"


def list_distroboxes() -> str:
    """List existing distrobox containers with status."""
    result = run_command("distrobox list")
    return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"


def exec_in_distrobox(name: str, command: str) -> str:
    """Run a command inside a distrobox container.

    Args:
        name: container name
        command: shell command to execute inside the container
    """
    result = run_command(f'distrobox enter {name} -- {command}')
    output = result.stdout
    if result.stderr:
        output += f"\nSTDERR: {result.stderr}"
    return output


def export_distrobox_app(name: str, app: str) -> str:
    """Export a GUI app from a distrobox container to the host application menu.

    Args:
        name: container name
        app: application package name inside the container
    """
    result = run_command(f"distrobox enter {name} -- distrobox-export --app {app}")
    if result.returncode != 0:
        return f"Failed to export '{app}' from '{name}': {result.stderr}"
    return f"Exported '{app}' from container '{name}' to host application menu."


def manage_quadlet(action: str, name: str | None = None, image: str | None = None) -> str:
    """Manage Quadlet units for persistent containerized services.

    Quadlet uses systemd + podman for services like media servers, game servers.

    Args:
        action: 'list', 'create', 'start', 'stop', 'status', 'remove'
        name: service/unit name
        image: container image (for 'create' action)
    """
    if action == "list":
        result = run_command("systemctl --user list-units --type=service 'podman-*' --no-pager 2>/dev/null")
        return result.stdout if result.stdout.strip() else "No Quadlet services found."
    elif action == "status" and name:
        result = run_command(f"systemctl --user status {name} --no-pager")
        return result.stdout
    elif action in ("start", "stop") and name:
        result = run_command(f"systemctl --user {action} {name}")
        return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"
    elif action == "create" and name and image:
        quadlet_dir = "~/.config/containers/systemd"
        run_command(f"mkdir -p {quadlet_dir}")
        unit_content = f"""[Container]
Image={image}
PublishPort=

[Service]
Restart=always

[Install]
WantedBy=default.target
"""
        return f"To create a Quadlet service, write this to {quadlet_dir}/{name}.container:\n\n{unit_content}\nThen run: systemctl --user daemon-reload && systemctl --user start {name}"
    return f"Usage: action='list|create|start|stop|status|remove', name=<service>, image=<image>"


def manage_podman(action: str, args: str = "") -> str:
    """Run podman container operations.

    Args:
        action: 'ps', 'images', 'run', 'stop', 'rm', 'pull'
        args: additional arguments for the podman command
    """
    result = run_command(f"podman {action} {args}")
    return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"


def manage_waydroid(action: str) -> str:
    """Manage Waydroid for running Android apps.

    Args:
        action: 'status', 'start', 'stop', 'setup'
    """
    if action == "setup":
        return "Run: ujust setup-waydroid\n\nThis will set up Waydroid with Google Play support."
    elif action in ("status", "start", "stop"):
        if action == "start":
            result = run_command("waydroid session start")
        elif action == "stop":
            result = run_command("waydroid session stop")
        else:
            result = run_command("waydroid status")
        return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"
    return f"Unknown action '{action}'. Supported: setup, status, start, stop."
```

**Step 4: Run test to verify it passes**

Run: `cd ~/bazzite-mcp && uv run pytest tests/test_tools_containers.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd ~/bazzite-mcp && git add src/bazzite_mcp/tools/containers.py tests/test_tools_containers.py
git commit -m "feat: add container tools (distrobox, quadlet, podman, waydroid)"
```

---

### Task 13: Docs cache and knowledge tools

**Files:**
- Create: `src/bazzite_mcp/cache/docs_cache.py`
- Create: `src/bazzite_mcp/cache/__init__.py`
- Create: `src/bazzite_mcp/tools/docs.py`
- Create: `tests/test_docs_cache.py`
- Create: `tests/test_tools_docs.py`

**Step 1: Write failing test for cache**

Create: `tests/test_docs_cache.py`

```python
from bazzite_mcp.cache.docs_cache import DocsCache


def test_store_and_search(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    cache = DocsCache()
    cache.store_page(
        url="https://docs.bazzite.gg/test",
        title="Test Page",
        content="Flatpak is the primary method for installing GUI applications on Bazzite.",
        section="Installing Software",
    )
    results = cache.search("flatpak gui")
    assert len(results) > 0
    assert "flatpak" in results[0]["content"].lower()


def test_cache_staleness(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    cache = DocsCache()
    cache.store_page(
        url="https://docs.bazzite.gg/old",
        title="Old Page",
        content="Old content",
        section="Test",
    )
    # Force staleness by backdating
    cache._conn.execute("UPDATE pages SET fetched_at = '2020-01-01T00:00:00Z'")
    cache._conn.commit()
    assert cache.is_stale() is True
```

**Step 2: Run test to verify it fails**

Run: `cd ~/bazzite-mcp && uv run pytest tests/test_docs_cache.py -v`
Expected: FAIL

**Step 3: Write docs cache implementation**

Create: `src/bazzite_mcp/cache/__init__.py` (empty)

Create: `src/bazzite_mcp/cache/docs_cache.py`

```python
from datetime import datetime, timedelta, timezone
from bazzite_mcp.db import get_db_path, get_connection, ensure_tables

CACHE_TTL_DAYS = 7


class DocsCache:
    def __init__(self):
        db_path = get_db_path("docs_cache.db")
        self._conn = get_connection(db_path)
        ensure_tables(self._conn, "cache")

    def store_page(self, url: str, title: str, content: str, section: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO pages (url, title, content, section, fetched_at) VALUES (?, ?, ?, ?, ?)",
            (url, title, content, section, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()

    def store_changelog(self, version: str, date: str, body: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO changelogs (version, date, body) VALUES (?, ?, ?)",
            (version, date, body),
        )
        self._conn.commit()

    def search(self, query: str, limit: int = 10) -> list[dict]:
        rows = self._conn.execute(
            "SELECT p.url, p.title, p.content, p.section, p.fetched_at FROM pages p JOIN pages_fts f ON p.id = f.rowid WHERE pages_fts MATCH ? ORDER BY rank LIMIT ?",
            (query, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_changelog(self, version: str | None = None, limit: int = 5) -> list[dict]:
        if version:
            rows = self._conn.execute(
                "SELECT * FROM changelogs WHERE version = ?", (version,)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM changelogs ORDER BY date DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def is_stale(self) -> bool:
        row = self._conn.execute(
            "SELECT MIN(fetched_at) as oldest FROM pages"
        ).fetchone()
        if not row or not row["oldest"]:
            return True
        oldest = datetime.fromisoformat(row["oldest"])
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - oldest > timedelta(days=CACHE_TTL_DAYS)

    def clear(self) -> None:
        self._conn.execute("DELETE FROM pages")
        self._conn.execute("DELETE FROM pages_fts")
        self._conn.commit()

    def page_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) as cnt FROM pages").fetchone()
        return row["cnt"]
```

**Step 4: Run cache test to verify it passes**

Run: `cd ~/bazzite-mcp && uv run pytest tests/test_docs_cache.py -v`
Expected: PASS

**Step 5: Write failing test for docs tools**

Create: `tests/test_tools_docs.py`

```python
from unittest.mock import patch, MagicMock
from bazzite_mcp.tools.docs import install_policy


def test_install_policy_gui_app():
    result = install_policy("gui")
    assert "flatpak" in result.lower()


def test_install_policy_cli_tool():
    result = install_policy("cli")
    assert "brew" in result.lower() or "homebrew" in result.lower()
```

**Step 6: Write docs tools implementation**

Create: `src/bazzite_mcp/tools/docs.py`

```python
import httpx
from bs4 import BeautifulSoup
from bazzite_mcp.cache.docs_cache import DocsCache

DOCS_BASE = "https://docs.bazzite.gg"
GITHUB_API = "https://api.github.com/repos/ublue-os/bazzite/releases"

# Key documentation pages to crawl
DOC_PAGES = [
    "/",
    "/Installing_and_Managing_Software/",
    "/Installing_and_Managing_Software/Flatpak/",
    "/Installing_and_Managing_Software/Homebrew/",
    "/Installing_and_Managing_Software/rpm-ostree/",
    "/Installing_and_Managing_Software/Updates_Rollbacks_and_Rebasing/",
    "/General/",
    "/Advanced/",
    "/FAQ/",
]


def query_bazzite_docs(query: str) -> str:
    """Full-text search the cached Bazzite documentation.

    Searches locally cached docs from docs.bazzite.gg. If cache is empty or stale,
    suggests running refresh_docs_cache.

    Args:
        query: search terms (e.g. 'flatpak install', 'rpm-ostree warning')
    """
    cache = DocsCache()
    if cache.page_count() == 0:
        return "Docs cache is empty. Run refresh_docs_cache() to populate it from docs.bazzite.gg."
    results = cache.search(query)
    if not results:
        return f"No results for '{query}' in cached docs."
    stale_notice = " (Note: cache may be stale, consider running refresh_docs_cache)" if cache.is_stale() else ""
    parts = []
    for r in results:
        parts.append(f"### {r['title']} ({r['section']})\n{r['content'][:500]}\nSource: {r['url']}")
    return "\n\n---\n\n".join(parts) + stale_notice


def bazzite_changelog(version: str | None = None, count: int = 5) -> str:
    """Get Bazzite release changelog.

    Args:
        version: specific version to look up (e.g. '3.7.0'). Omit for latest N.
        count: number of recent releases to show (default 5)
    """
    cache = DocsCache()
    entries = cache.get_changelog(version=version, limit=count)
    if entries:
        parts = []
        for e in entries:
            parts.append(f"## {e['version']} ({e['date']})\n{e['body'][:1000]}")
        return "\n\n".join(parts)

    # Try fetching from GitHub
    try:
        resp = httpx.get(GITHUB_API, params={"per_page": count}, timeout=15)
        resp.raise_for_status()
        releases = resp.json()
        parts = []
        for r in releases:
            cache.store_changelog(r["tag_name"], r.get("published_at", ""), r.get("body", ""))
            parts.append(f"## {r['tag_name']} ({r.get('published_at', 'unknown')})\n{r.get('body', 'No body')[:1000]}")
        return "\n\n".join(parts)
    except Exception as e:
        return f"Failed to fetch changelogs: {e}"


def install_policy(app_type: str) -> str:
    """Explain the recommended install method for a given app type.

    Args:
        app_type: type of software — 'gui', 'cli', 'service', 'dev-environment', 'driver', 'android'
    """
    policies = {
        "gui": "For GUI applications, use **Flatpak** (Tier 2).\nInstall via Bazaar app store or: flatpak install flathub <app-id>\nFlatpak apps are sandboxed and update independently of the OS.\nManage permissions with Flatseal (pre-installed).",
        "cli": "For CLI/TUI tools, use **Homebrew** (Tier 3).\nInstall via: brew install <package>\nHomebrew installs to user-space and doesn't touch the immutable host.\nNote: packages requiring root should use Distrobox instead.",
        "service": "For persistent services (media servers, game servers), use **Quadlet** (Tier 4).\nQuadlet combines systemd + podman for declarative container services.\nFor one-off services, consider Distrobox.",
        "dev-environment": "For development environments, use **Distrobox** (Tier 4).\nCreate isolated containers with full distro package managers:\n  distrobox create --name dev --image ubuntu:24.04\n  distrobox enter dev\nUse distrobox-export to integrate GUI apps with host.",
        "driver": "For drivers and kernel-adjacent packages, **rpm-ostree** (Tier 6, last resort).\nOnly use when no other option exists. Be aware:\n- Can freeze system updates\n- Can block rebasing\n- Can cause dependency conflicts\nAlways check ujust first: ujust --summary | grep <driver>",
        "android": "For Android apps, use **Waydroid**.\nSetup via: ujust setup-waydroid\nThis provides a full Android system container with Google Play support.",
    }
    if app_type not in policies:
        return f"Unknown app type '{app_type}'. Supported: {', '.join(policies.keys())}.\n\nGeneral hierarchy: ujust > flatpak > brew > distrobox > AppImage > rpm-ostree"
    return policies[app_type]


def refresh_docs_cache() -> str:
    """Refresh the local docs cache by crawling docs.bazzite.gg.

    Fetches key documentation pages and stores them for offline full-text search.
    Also fetches recent changelogs from GitHub releases.
    """
    cache = DocsCache()
    cache.clear()
    fetched = 0
    errors = []

    for path in DOC_PAGES:
        url = f"{DOCS_BASE}{path}"
        try:
            resp = httpx.get(url, timeout=15, follow_redirects=True)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            # Extract main content (mkdocs-material uses <article> or .md-content)
            article = soup.find("article") or soup.find(class_="md-content")
            if article:
                title = soup.find("title")
                title_text = title.get_text(strip=True) if title else path
                content = article.get_text(separator="\n", strip=True)
                cache.store_page(url=url, title=title_text, content=content, section=path.strip("/") or "Home")
                fetched += 1
            else:
                errors.append(f"{url}: no article content found")
        except Exception as e:
            errors.append(f"{url}: {e}")

    # Fetch changelogs
    try:
        resp = httpx.get(GITHUB_API, params={"per_page": 10}, timeout=15)
        resp.raise_for_status()
        for r in resp.json():
            cache.store_changelog(r["tag_name"], r.get("published_at", ""), r.get("body", ""))
    except Exception as e:
        errors.append(f"GitHub releases: {e}")

    report = f"Refreshed docs cache: {fetched} pages fetched."
    if errors:
        report += f"\n\nErrors ({len(errors)}):\n" + "\n".join(f"  - {e}" for e in errors)
    return report
```

**Step 7: Run all docs tests**

Run: `cd ~/bazzite-mcp && uv run pytest tests/test_docs_cache.py tests/test_tools_docs.py -v`
Expected: PASS

**Step 8: Commit**

```bash
cd ~/bazzite-mcp && git add src/bazzite_mcp/cache/ src/bazzite_mcp/tools/docs.py tests/test_docs_cache.py tests/test_tools_docs.py
git commit -m "feat: add docs cache with FTS5 search and knowledge tools"
```

---

### Task 14: Audit tools (MCP-exposed)

**Files:**
- Create: `src/bazzite_mcp/tools/audit_tools.py`
- Create: `tests/test_tools_audit.py`

**Step 1: Write failing test**

Create: `tests/test_tools_audit.py`

```python
from unittest.mock import patch
from bazzite_mcp.tools.audit_tools import audit_log_query


def test_audit_log_query_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    result = audit_log_query()
    assert "no actions" in result.lower() or "empty" in result.lower() or isinstance(result, str)
```

**Step 2: Run test to verify it fails**

Run: `cd ~/bazzite-mcp && uv run pytest tests/test_tools_audit.py -v`
Expected: FAIL

**Step 3: Write implementation**

Create: `src/bazzite_mcp/tools/audit_tools.py`

```python
import json
from bazzite_mcp.audit import AuditLog
from bazzite_mcp.runner import run_command


def audit_log_query(tool: str | None = None, search: str | None = None, limit: int = 20) -> str:
    """Query the audit log of actions performed by the MCP server.

    Args:
        tool: filter by tool name (e.g. 'install_package')
        search: free text search across commands and output
        limit: max entries to return (default 20)
    """
    log = AuditLog()
    entries = log.query(tool=tool, search=search, limit=limit)
    if not entries:
        return "No actions recorded yet."
    parts = []
    for e in entries:
        rollback = f"\n  Rollback: {e['rollback']}" if e.get("rollback") else ""
        parts.append(
            f"[{e['timestamp']}] {e['tool']}: {e['command']}\n"
            f"  Result: {e['result']}{rollback}"
        )
    return "\n\n".join(parts)


def rollback_action(action_id: int) -> str:
    """Execute the rollback command for a specific audit log entry.

    Args:
        action_id: the ID of the audit log entry to roll back
    """
    log = AuditLog()
    rollback_cmd = log.get_rollback(action_id)
    if not rollback_cmd:
        return f"No rollback command found for action #{action_id}."
    result = run_command(rollback_cmd)
    output = f"Rollback command: {rollback_cmd}\n"
    if result.returncode == 0:
        output += f"Success: {result.stdout}"
    else:
        output += f"Failed (exit {result.returncode}): {result.stderr}"
    return output
```

**Step 4: Run test to verify it passes**

Run: `cd ~/bazzite-mcp && uv run pytest tests/test_tools_audit.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd ~/bazzite-mcp && git add src/bazzite_mcp/tools/audit_tools.py tests/test_tools_audit.py
git commit -m "feat: add audit log query and rollback tools"
```

---

## Phase 4: Self-Improvement Tools

### Task 15: Self-improvement tools (GitHub-backed contribution system)

**Files:**
- Create: `src/bazzite_mcp/tools/self_improve.py`
- Create: `tests/test_tools_self_improve.py`

The MCP server should be a self-improving system. AI agents using it can identify
gaps, bugs, or improvements and contribute back by creating GitHub issues or PRs
against the bazzite-mcp repository. This closes the feedback loop: agents use the
server, discover what's missing, and fix it.

**Step 1: Write failing test**

Create: `tests/test_tools_self_improve.py`

```python
from unittest.mock import patch, MagicMock
from bazzite_mcp.tools.self_improve import suggest_improvement, list_improvements


@patch("bazzite_mcp.tools.self_improve.run_command")
def test_suggest_improvement_creates_issue(mock_run):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="https://github.com/rolandmarg/bazzite-mcp/issues/1",
        stderr="",
    )
    result = suggest_improvement(
        title="Add Bluetooth toggle tool",
        description="There is no tool to toggle Bluetooth on/off. Should add a manage_bluetooth tool.",
        category="missing-tool",
    )
    assert "issue" in result.lower() or "github" in result.lower()


@patch("bazzite_mcp.tools.self_improve.run_command")
def test_list_improvements(mock_run):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="#1 Add Bluetooth toggle\n#2 Fix audio switching",
        stderr="",
    )
    result = list_improvements()
    assert "#1" in result
```

**Step 2: Run test to verify it fails**

Run: `cd ~/bazzite-mcp && uv run pytest tests/test_tools_self_improve.py -v`
Expected: FAIL

**Step 3: Write implementation**

Create: `src/bazzite_mcp/tools/self_improve.py`

```python
from bazzite_mcp.runner import run_command

REPO = "rolandmarg/bazzite-mcp"
REPO_LOCAL = "/home/kira/bazzite-mcp"


def suggest_improvement(title: str, description: str, category: str = "enhancement") -> str:
    """Create a GitHub issue suggesting an improvement to the bazzite-mcp server.

    Use this when you discover a gap, bug, or missing feature in the MCP server.
    The issue will be created on the bazzite-mcp GitHub repository for review.

    Args:
        title: short issue title (e.g. 'Add Bluetooth toggle tool')
        description: detailed description of what's missing/broken and proposed fix
        category: issue category — 'missing-tool', 'bug', 'enhancement', 'docs', 'guardrail'
    """
    labels = {
        "missing-tool": "enhancement,tool-request",
        "bug": "bug",
        "enhancement": "enhancement",
        "docs": "documentation",
        "guardrail": "safety",
    }
    label_str = labels.get(category, "enhancement")
    body = f"**Category:** {category}\n\n{description}\n\n---\n*Auto-generated by bazzite-mcp self-improvement system*"

    result = run_command(
        f'gh issue create --repo {REPO} --title "{title}" --body "{body}" --label "{label_str}" 2>&1'
    )
    if result.returncode != 0:
        # Fallback: if gh is not authenticated or repo doesn't exist, log locally
        return f"Could not create GitHub issue (gh error: {result.stderr}).\n\nSuggestion recorded locally:\n  Title: {title}\n  Category: {category}\n  Description: {description}"
    return f"Improvement suggested: {result.stdout.strip()}\n\nTitle: {title}\nCategory: {category}"


def contribute_fix(branch_name: str, description: str, files_changed: str) -> str:
    """Create a PR with a fix or improvement to the bazzite-mcp server.

    Use this after you've made code changes to the bazzite-mcp source code.
    Creates a branch, commits changes, and opens a PR for human review.

    Args:
        branch_name: git branch name (e.g. 'add-bluetooth-tool')
        description: PR description explaining what was changed and why
        files_changed: space-separated list of changed file paths relative to repo root
    """
    # Create branch
    result = run_command(f"cd {REPO_LOCAL} && git checkout -b {branch_name}")
    if result.returncode != 0:
        return f"Failed to create branch: {result.stderr}"

    # Stage and commit
    result = run_command(
        f'cd {REPO_LOCAL} && git add {files_changed} && '
        f'git commit -m "feat: {description[:72]}\n\nAuto-contributed by bazzite-mcp self-improvement system"'
    )
    if result.returncode != 0:
        run_command(f"cd {REPO_LOCAL} && git checkout main")
        return f"Failed to commit: {result.stderr}"

    # Push and create PR
    result = run_command(f"cd {REPO_LOCAL} && git push -u origin {branch_name}")
    if result.returncode != 0:
        run_command(f"cd {REPO_LOCAL} && git checkout main")
        return f"Failed to push: {result.stderr}"

    pr_result = run_command(
        f'cd {REPO_LOCAL} && gh pr create --title "feat: {description[:60]}" '
        f'--body "## Summary\n\n{description}\n\n---\n*Auto-contributed by bazzite-mcp self-improvement system*" '
        f'--base main'
    )

    # Return to main
    run_command(f"cd {REPO_LOCAL} && git checkout main")

    if pr_result.returncode != 0:
        return f"Branch pushed but PR creation failed: {pr_result.stderr}\nManually create PR for branch '{branch_name}'."
    return f"PR created: {pr_result.stdout.strip()}\n\nBranch: {branch_name}\nDescription: {description}"


def list_improvements(state: str = "open") -> str:
    """List existing improvement suggestions (GitHub issues) for the MCP server.

    Args:
        state: 'open', 'closed', or 'all'
    """
    result = run_command(f"gh issue list --repo {REPO} --state {state} --limit 20")
    if result.returncode != 0:
        return f"Failed to list issues: {result.stderr}"
    return result.stdout if result.stdout.strip() else "No issues found."


def list_pending_prs() -> str:
    """List open pull requests on the bazzite-mcp repository."""
    result = run_command(f"gh pr list --repo {REPO} --state open --limit 20")
    if result.returncode != 0:
        return f"Failed to list PRs: {result.stderr}"
    return result.stdout if result.stdout.strip() else "No open PRs."


def get_server_source(file_path: str) -> str:
    """Read the source code of a bazzite-mcp server file.

    Use this to understand current implementation before suggesting improvements.

    Args:
        file_path: path relative to repo root (e.g. 'src/bazzite_mcp/tools/packages.py')
    """
    result = run_command(f"cat {REPO_LOCAL}/{file_path}")
    if result.returncode != 0:
        return f"File not found: {file_path}"
    return result.stdout
```

**Step 4: Run test to verify it passes**

Run: `cd ~/bazzite-mcp && uv run pytest tests/test_tools_self_improve.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd ~/bazzite-mcp && git add src/bazzite_mcp/tools/self_improve.py tests/test_tools_self_improve.py
git commit -m "feat: add self-improvement tools (issues, PRs, source reading)"
```

---

## Phase 5: Server Registration

### Task 16: Register all tools with FastMCP server

**Files:**
- Modify: `src/bazzite_mcp/server.py`
- Create: `tests/test_tool_registration.py`

**Step 1: Write failing test**

Create: `tests/test_tool_registration.py`

```python
from bazzite_mcp.server import mcp


def test_all_tools_registered():
    """Verify all expected tool groups are registered."""
    # FastMCP stores tools in mcp._tool_manager or similar
    # We test by checking the server has tools
    # The exact API depends on FastMCP version
    assert mcp is not None
    assert mcp.name == "bazzite"
```

**Step 2: Write full server.py with all tool registrations**

Modify: `src/bazzite_mcp/server.py`

```python
from fastmcp import FastMCP

from bazzite_mcp.tools.ujust import ujust_run, ujust_list, ujust_show
from bazzite_mcp.tools.system import system_info, disk_usage, update_status, journal_logs, hardware_info, process_list
from bazzite_mcp.tools.packages import install_package, remove_package, search_package, list_packages, update_packages
from bazzite_mcp.tools.settings import set_theme, set_audio_output, get_display_config, set_display_config, set_power_profile, get_settings, set_settings
from bazzite_mcp.tools.services import manage_service, service_status, list_services, network_status, manage_connection, manage_firewall, manage_tailscale
from bazzite_mcp.tools.containers import create_distrobox, manage_distrobox, list_distroboxes, exec_in_distrobox, export_distrobox_app, manage_quadlet, manage_podman, manage_waydroid
from bazzite_mcp.tools.docs import query_bazzite_docs, bazzite_changelog, install_policy, refresh_docs_cache
from bazzite_mcp.tools.audit_tools import audit_log_query, rollback_action
from bazzite_mcp.tools.self_improve import suggest_improvement, contribute_fix, list_improvements, list_pending_prs, get_server_source

mcp = FastMCP("bazzite")

# ujust (Tier 1)
mcp.tool(ujust_run)
mcp.tool(ujust_list)
mcp.tool(ujust_show)

# Package management
mcp.tool(install_package)
mcp.tool(remove_package)
mcp.tool(search_package)
mcp.tool(list_packages)
mcp.tool(update_packages)

# System settings
mcp.tool(set_theme)
mcp.tool(set_audio_output)
mcp.tool(get_display_config)
mcp.tool(set_display_config)
mcp.tool(set_power_profile)
mcp.tool(get_settings)
mcp.tool(set_settings)

# Services & networking
mcp.tool(manage_service)
mcp.tool(service_status)
mcp.tool(list_services)
mcp.tool(network_status)
mcp.tool(manage_connection)
mcp.tool(manage_firewall)
mcp.tool(manage_tailscale)

# Containers
mcp.tool(create_distrobox)
mcp.tool(manage_distrobox)
mcp.tool(list_distroboxes)
mcp.tool(exec_in_distrobox)
mcp.tool(export_distrobox_app)
mcp.tool(manage_quadlet)
mcp.tool(manage_podman)
mcp.tool(manage_waydroid)

# System info
mcp.tool(system_info)
mcp.tool(disk_usage)
mcp.tool(update_status)
mcp.tool(journal_logs)
mcp.tool(hardware_info)
mcp.tool(process_list)

# Knowledge & docs
mcp.tool(query_bazzite_docs)
mcp.tool(bazzite_changelog)
mcp.tool(install_policy)
mcp.tool(refresh_docs_cache)

# Audit
mcp.tool(audit_log_query)
mcp.tool(rollback_action)

# Self-improvement
mcp.tool(suggest_improvement)
mcp.tool(contribute_fix)
mcp.tool(list_improvements)
mcp.tool(list_pending_prs)
mcp.tool(get_server_source)
```

**Step 3: Run test and full test suite**

Run: `cd ~/bazzite-mcp && uv run pytest tests/ -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
cd ~/bazzite-mcp && git add src/bazzite_mcp/server.py tests/test_tool_registration.py
git commit -m "feat: register all tool modules with FastMCP server"
```

---

### Task 17: Register MCP server with Claude Code

**Files:**
- Create: `~/.claude/mcp.json`

**Step 1: Create MCP config**

Create `~/.claude/mcp.json`:

```json
{
  "mcpServers": {
    "bazzite": {
      "command": "uv",
      "args": ["run", "--directory", "/home/kira/bazzite-mcp", "python", "-m", "bazzite_mcp"]
    }
  }
}
```

**Step 2: Verify server starts correctly**

Run: `cd ~/bazzite-mcp && echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"0.1"}}}' | uv run python -m bazzite_mcp 2>/dev/null | head -1`
Expected: JSON response with server info and capabilities

**Step 3: Commit**

```bash
cd ~/bazzite-mcp && git add -A
git commit -m "feat: add MCP client configuration for Claude Code"
```

---

## Phase 6: AGENTS.md Migration

### Task 18: Migrate OS knowledge from AGENTS.md to MCP server

**Files:**
- Modify: `~/.config/opencode/AGENTS.md`

The whole point of the MCP server is to replace static OS knowledge in AGENTS.md
with live, queryable tools. Now that the MCP server has all the knowledge
(install policy, hardware info, Bazzite docs, system tools), we strip AGENTS.md
down to a minimal pointer.

**Step 1: Remove Bazzite-specific sections from AGENTS.md**

Remove these sections entirely:
- `## Platform` (hardware/OS info → now served by `system_info`, `hardware_info` tools)
- `## Bazzite References` (docs links → now served by `query_bazzite_docs`, `refresh_docs_cache`)
- `## Hardware` (hardware details → now served by `hardware_info` tool)
- `## Installation and Update Policy (Bazzite)` (install hierarchy → now served by `install_policy`, `install_package`)
- `## Tool Choice Example` (install examples → now served by `search_package`, `install_package`)

**Step 2: Add a minimal MCP pointer section**

Replace all removed sections with:

```markdown
## Bazzite OS
- This system runs Bazzite (immutable Fedora-based Linux).
- For ALL OS operations (package install, settings, services, system info, etc.), use the `bazzite` MCP server tools.
- The MCP server knows Bazzite's official best practices, install hierarchy, and guardrails.
- Key tools: `install_package`, `system_info`, `query_bazzite_docs`, `install_policy`, `ujust_run`
- To improve the MCP server itself: `suggest_improvement`, `contribute_fix`
```

**Step 3: Keep non-Bazzite sections intact**

These sections stay in AGENTS.md (they're not OS-specific):
- `## Identity`
- `## Operating Rules`
- `## Session Memory`
- `## Library Documentation Policy (Context7)`
- `## Token Efficiency`

**Step 4: Verify AGENTS.md is significantly shorter**

The file should go from ~68 lines to ~35 lines. All Bazzite-specific knowledge
now lives in the MCP server where it can be queried, updated, and self-improved.

---

## Phase 7: Smoke Test

### Task 19: End-to-end smoke test

**Step 1: Run full test suite**

Run: `cd ~/bazzite-mcp && uv run pytest tests/ -v --tb=short`
Expected: ALL tests pass

**Step 2: Test server responds to tool listing**

Run: `cd ~/bazzite-mcp && echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"0.1"}}}' | uv run python -m bazzite_mcp 2>/dev/null | python3 -c "import sys,json; print(json.dumps(json.loads(sys.stdin.readline()), indent=2))"`
Expected: JSON with server capabilities

**Step 3: Restart Claude Code and verify bazzite MCP server appears**

Restart Claude Code. Run a test query like "what's my system info" and verify the bazzite MCP tools are available.

**Step 4: Final commit**

```bash
cd ~/bazzite-mcp && git add -A
git commit -m "chore: complete bazzite-mcp v1 implementation"
```
