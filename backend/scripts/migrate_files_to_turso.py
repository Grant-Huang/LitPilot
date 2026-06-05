#!/usr/bin/env python3
"""
Import local FileStore data/ directory into Turso.

Usage (from backend/):
  python scripts/migrate_files_to_turso.py --data-dir ../data
  python scripts/migrate_files_to_turso.py --data-dir ../data --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from dotenv import load_dotenv

load_dotenv(BACKEND_ROOT.parent / ".env")
load_dotenv(BACKEND_ROOT / ".env")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default):
    if not path.is_file():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def import_sessions(conn, data_dir: Path, *, dry_run: bool) -> dict[str, int]:
    stats = {"sessions": 0, "messages": 0, "artifacts": 0, "documents": 0}
    sessions_root = data_dir / "sessions"
    if not sessions_root.is_dir():
        return stats

    index = _read_json(sessions_root / "index.json", {"sessions": []})
    for entry in index.get("sessions") or []:
        sid = str(entry.get("id") or "")
        if not sid:
            continue
        meta_path = sessions_root / sid / "meta.json"
        if not meta_path.is_file():
            continue
        meta = _read_json(meta_path, {})
        title = str(meta.get("title") or entry.get("title") or "新综述")
        pinned = 1 if meta.get("pinned") else 0
        created_at = str(meta.get("created_at") or _utc_now())
        updated_at = str(meta.get("updated_at") or created_at)
        extra_meta = {
            k: v
            for k, v in meta.items()
            if k not in ("id", "title", "pinned", "created_at", "updated_at")
        }
        stats["sessions"] += 1
        if dry_run:
            continue
        conn.execute(
            """
            INSERT INTO sessions (id, title, pinned, created_at, updated_at, meta_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,
                pinned=excluded.pinned,
                updated_at=excluded.updated_at,
                meta_json=excluded.meta_json
            """,
            (sid, title, pinned, created_at, updated_at, json.dumps(extra_meta, ensure_ascii=False)),
        )

        msg_path = sessions_root / sid / "messages.jsonl"
        if msg_path.is_file():
            seq = 0
            for line in msg_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                seq += 1
                stats["messages"] += 1
                if dry_run:
                    continue
                conn.execute(
                    """
                    INSERT INTO session_messages
                        (session_id, seq, role, content, meta_json, ts)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_id, seq) DO UPDATE SET
                        role=excluded.role,
                        content=excluded.content,
                        meta_json=excluded.meta_json,
                        ts=excluded.ts
                    """,
                    (
                        sid,
                        seq,
                        str(rec.get("role") or ""),
                        str(rec.get("content") or ""),
                        json.dumps(rec.get("meta")) if rec.get("meta") else None,
                        str(rec.get("ts") or _utc_now()),
                    ),
                )

        for doc_type, filename in (("corpus", "corpus.json"), ("outline", "outline.json")):
            doc_path = sessions_root / sid / filename
            if not doc_path.is_file():
                continue
            payload = _read_json(doc_path, {})
            stats["documents"] += 1
            if dry_run:
                continue
            conn.execute(
                """
                INSERT INTO session_documents (session_id, doc_type, content_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id, doc_type) DO UPDATE SET
                    content_json=excluded.content_json,
                    updated_at=excluded.updated_at
                """,
                (
                    sid,
                    doc_type,
                    json.dumps(payload, ensure_ascii=False),
                    str(payload.get("updated_at") or _utc_now()),
                ),
            )

        art_root = data_dir / "artifacts" / sid
        if art_root.is_dir():
            for kind in ("review", "matrix"):
                latest = art_root / f"{kind}-latest.md"
                if not latest.is_file():
                    continue
                content = latest.read_text(encoding="utf-8")
                stats["artifacts"] += 1
                if dry_run:
                    continue
                artifact_id = f"{kind}_{sid}"
                conn.execute(
                    "UPDATE session_artifacts SET is_latest=0 WHERE session_id=? AND kind=?",
                    (sid, kind),
                )
                conn.execute(
                    """
                    INSERT INTO session_artifacts
                        (id, session_id, kind, filename, content, is_latest, created_at)
                    VALUES (?, ?, ?, ?, ?, 1, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        content=excluded.content,
                        is_latest=1,
                        created_at=excluded.created_at
                    """,
                    (
                        artifact_id,
                        sid,
                        kind,
                        f"{kind}-latest.md",
                        content,
                        _utc_now(),
                    ),
                )

    return stats


def import_config(conn, data_dir: Path, *, dry_run: bool) -> int:
    count = 0
    mapping = {
        "system.credentials.json": "system.credentials",
        "system.instances.json": "system.instances",
        "system.capabilities.json": "system.capabilities",
        "personal.preferences.json": "personal.preferences",
        "agent.json": "agent.legacy",
    }
    config_dir = data_dir / "config"
    for filename, key in mapping.items():
        path = config_dir / filename
        if not path.is_file():
            continue
        payload = _read_json(path, {})
        count += 1
        if dry_run:
            continue
        conn.execute(
            """
            INSERT INTO config_documents (doc_key, content_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(doc_key) DO UPDATE SET
                content_json=excluded.content_json,
                updated_at=excluded.updated_at
            """,
            (key, json.dumps(payload, ensure_ascii=False), _utc_now()),
        )
    return count


def import_library(conn, data_dir: Path, *, dry_run: bool) -> int:
    lib_path = data_dir / "refs" / "library.json"
    if not lib_path.is_file():
        return 0
    db = _read_json(lib_path, {})
    items = db.get("items") or {}
    next_idx = int(db.get("next_display_index") or 0)
    count = 0
    if not dry_run:
        conn.execute(
            """
            UPDATE library_meta
            SET next_display_index=?, version=?, updated_at=?
            WHERE id=1
            """,
            (next_idx, int(db.get("version") or 1), _utc_now()),
        )
    keys = db.get("keys") or {}
    for item_id, item in items.items():
        if not isinstance(item, dict):
            continue
        count += 1
        if dry_run:
            continue
        canonical = None
        for k, v in keys.items():
            if v == item_id:
                canonical = k
                break
        conn.execute(
            """
            INSERT INTO library_items (id, canonical_key, display_index, item_json, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                canonical_key=excluded.canonical_key,
                display_index=excluded.display_index,
                item_json=excluded.item_json,
                updated_at=excluded.updated_at
            """,
            (
                item_id,
                canonical,
                int(item.get("display_index") or 0),
                json.dumps(item, ensure_ascii=False),
                str(item.get("updated_at") or _utc_now()),
            ),
        )
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="Import local data/ into Turso")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=BACKEND_ROOT.parent / "data",
        help="LitPilot data directory (default: ../data)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Count only, no writes")
    args = parser.parse_args()

    data_dir = args.data_dir.resolve()
    if not data_dir.is_dir():
        print(f"ERROR: data dir not found: {data_dir}", file=sys.stderr)
        return 1

    from app.storage.turso_db import apply_migrations, get_connection

    if not args.dry_run:
        apply_migrations()

    conn = get_connection()
    try:
        sess = import_sessions(conn, data_dir, dry_run=args.dry_run)
        cfg = import_config(conn, data_dir, dry_run=args.dry_run)
        lib = import_library(conn, data_dir, dry_run=args.dry_run)
        if not args.dry_run:
            conn.commit()
    finally:
        conn.close()

    print(f"data_dir: {data_dir}")
    print(f"sessions: {sess['sessions']}, messages: {sess['messages']}, "
          f"artifacts: {sess['artifacts']}, documents: {sess['documents']}")
    print(f"config_documents: {cfg}, library_items: {lib}")
    if args.dry_run:
        print("(dry-run — no data written)")
    else:
        print("Import complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
