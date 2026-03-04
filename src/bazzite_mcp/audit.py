from __future__ import annotations

from bazzite_mcp.db import ensure_tables, get_connection, get_db_path


class AuditLog:
    def __init__(self) -> None:
        db_path = get_db_path("audit_log.db")
        self._conn = get_connection(db_path)
        ensure_tables(self._conn, "audit")

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> AuditLog:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

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
        return int(cursor.lastrowid)

    def query(
        self,
        tool: str | None = None,
        search: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        sql = "SELECT * FROM actions WHERE 1=1"
        params: list[object] = []
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
        row = self._conn.execute(
            "SELECT rollback FROM actions WHERE id = ?", (action_id,)
        ).fetchone()
        return row["rollback"] if row else None
