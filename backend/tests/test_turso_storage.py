"""Turso schema and migration tooling tests."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.storage.turso_db import (
    _split_sql_statements,
    applied_versions,
    list_migration_files,
    turso_configured,
)
from app.storage.turso_http import _encode_arg, libsql_url_to_https, pipeline_url


def test_list_migration_files_includes_core_schema() -> None:
    files = list_migration_files()
    names = [name for _, name, _ in files]
    assert "001_core.sql" in names
    assert "002_commercial.sql" in names


def test_libsql_url_to_https() -> None:
    raw = "libsql://litpilot-dev-grant-huang.aws-us-east-1.turso.io"
    assert libsql_url_to_https(raw) == "https://litpilot-dev-grant-huang.aws-us-east-1.turso.io"
    assert pipeline_url(raw).endswith("/v2/pipeline")


def test_encode_arg_types() -> None:
    assert _encode_arg(None)["type"] == "null"
    assert _encode_arg(42)["value"] == "42"
    assert _encode_arg("hello")["type"] == "text"


def test_split_sql_statements_basic() -> None:
    sql = "CREATE TABLE a (id INT); INSERT INTO a VALUES (1);"
    parts = _split_sql_statements(sql)
    assert len(parts) == 2
    assert "CREATE TABLE a" in parts[0]
    assert "INSERT INTO a" in parts[1]


@pytest.mark.skipif(not turso_configured(), reason="TURSO_DATABASE_URL not set")
def test_apply_migrations_idempotent() -> None:
    from app.storage.turso_db import apply_migrations, get_connection

    first = apply_migrations()
    second = apply_migrations()
    assert second == []
    conn = get_connection()
    try:
        versions = applied_versions(conn)
        assert 1 in versions
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "sessions" in tables
        assert "session_messages" in tables
        assert "config_documents" in tables
        assert "library_items" in tables
    finally:
        conn.close()


@pytest.mark.skipif(not turso_configured(), reason="TURSO_DATABASE_URL not set")
def test_migrate_files_dry_run(tmp_path: Path) -> None:
    import subprocess
    import sys

    data = tmp_path / "data"
    (data / "sessions").mkdir(parents=True)
    (data / "sessions" / "index.json").write_text(
        '{"sessions":[{"id":"abc123","title":"测试"}]}',
        encoding="utf-8",
    )
    sess_dir = data / "sessions" / "abc123"
    sess_dir.mkdir()
    (sess_dir / "meta.json").write_text(
        '{"id":"abc123","title":"测试","created_at":"2020-01-01T00:00:00+00:00",'
        '"updated_at":"2020-01-01T00:00:00+00:00"}',
        encoding="utf-8",
    )
    backend_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    proc = subprocess.run(
        [
            sys.executable,
            str(backend_root / "scripts" / "migrate_files_to_turso.py"),
            "--data-dir",
            str(data),
            "--dry-run",
        ],
        cwd=str(backend_root),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "sessions: 1" in proc.stdout
