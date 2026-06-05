"""Turso connection and schema migration runner (HTTP transport)."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.storage.turso_http import TursoHttpConnection, get_connection

_SCHEMA_DIR = Path(__file__).resolve().parent / "schema"
_MIGRATION_RE = re.compile(r"^(\d+)_.+\.sql$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def turso_configured() -> bool:
    import os

    return bool(os.getenv("TURSO_DATABASE_URL", "").strip())


def list_migration_files() -> list[tuple[int, str, Path]]:
    files: list[tuple[int, str, Path]] = []
    if not _SCHEMA_DIR.is_dir():
        return files
    for path in sorted(_SCHEMA_DIR.glob("*.sql")):
        match = _MIGRATION_RE.match(path.name)
        if not match:
            continue
        version = int(match.group(1))
        files.append((version, path.name, path))
    return files


def applied_versions(conn: TursoHttpConnection) -> set[int]:
    try:
        rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    except Exception:
        return set()
    return {int(row[0]) for row in rows}


def _split_sql_statements(sql: str) -> list[str]:
    """Split SQL file on semicolons outside of strings and line comments."""
    statements: list[str] = []
    buf: list[str] = []
    in_single = False
    in_line_comment = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""
        if in_line_comment:
            buf.append(ch)
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue
        if not in_single and ch == "-" and nxt == "-":
            in_line_comment = True
            buf.append(ch)
            buf.append(nxt)
            i += 2
            continue
        if ch == "'" and not in_single:
            in_single = True
            buf.append(ch)
        elif ch == "'" and in_single:
            if nxt == "'":
                buf.append("''")
                i += 2
                continue
            in_single = False
            buf.append(ch)
        elif ch == ";" and not in_single:
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def apply_migrations(conn: TursoHttpConnection | None = None) -> list[str]:
    """Apply pending SQL migrations. Returns names of applied files."""
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    applied: list[str] = []
    done = applied_versions(conn)
    for version, name, path in list_migration_files():
        if version in done:
            continue
        sql = path.read_text(encoding="utf-8")
        statements = _split_sql_statements(sql)
        if statements:
            for stmt in statements:
                try:
                    conn.execute(stmt)
                except RuntimeError as exc:
                    msg = str(exc).lower()
                    if "duplicate column name" not in msg:
                        raise
        conn.execute(
            "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
            (version, name, _utc_now()),
        )
        applied.append(name)
    if own_conn:
        conn.close()
    return applied


def execute_query(sql: str, params: tuple[Any, ...] | list[Any] = ()) -> TursoHttpConnection:
    conn = get_connection()
    conn.execute(sql, params)
    return conn


def fetchall(sql: str, params: tuple[Any, ...] | list[Any] = ()) -> list[tuple]:
    conn = get_connection()
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def fetchone(sql: str, params: tuple[Any, ...] | list[Any] = ()) -> tuple | None:
    conn = get_connection()
    try:
        return conn.execute(sql, params).fetchone()
    finally:
        conn.close()
