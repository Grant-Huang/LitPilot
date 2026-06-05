"""Turso SQL repository for LitPilot persistence."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from app.storage.turso_http import TursoHttpConnection, get_connection

_SESSION_COLS = frozenset(
    {"id", "title", "pinned", "created_at", "updated_at", "tenant_id", "title_auto_set"}
)

_CONFIG_LIST_KEYS = frozenset(
    {
        "system.credentials",
        "system.instances",
        "system.capabilities",
    }
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_tenant_id() -> str:
    return str(os.getenv("LITPILOT_TENANT_ID", "default") or "default").strip() or "default"


class TursoRepo:
    def __init__(self, conn: TursoHttpConnection | None = None) -> None:
        self._conn = conn or get_connection()
        self._own_conn = conn is None

    def close(self) -> None:
        if self._own_conn:
            self._conn.close()

    def has_config(self, doc_key: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM config_documents WHERE doc_key = ? LIMIT 1",
            (doc_key,),
        ).fetchone()
        return row is not None

    def get_config_raw(self, doc_key: str) -> Any | None:
        row = self._conn.execute(
            "SELECT content_json FROM config_documents WHERE doc_key = ?",
            (doc_key,),
        ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except (TypeError, json.JSONDecodeError):
            return None

    def set_config_raw(self, doc_key: str, data: Any) -> None:
        self._conn.execute(
            """
            INSERT INTO config_documents (doc_key, content_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(doc_key) DO UPDATE SET
                content_json = excluded.content_json,
                updated_at = excluded.updated_at
            """,
            (doc_key, json.dumps(data, ensure_ascii=False), _utc_now()),
        )

    def get_config_list(self, doc_key: str) -> list[dict[str, Any]]:
        raw = self.get_config_raw(doc_key)
        if isinstance(raw, list):
            return [dict(x) for x in raw if isinstance(x, dict)]
        if isinstance(raw, dict):
            items = raw.get("items")
            if isinstance(items, list):
                return [dict(x) for x in items if isinstance(x, dict)]
        return []

    def set_config_list(self, doc_key: str, items: list[dict[str, Any]]) -> None:
        self.set_config_raw(doc_key, {"items": items, "updated_at": _utc_now()})

    def get_config_obj(self, doc_key: str, default: dict[str, Any]) -> dict[str, Any]:
        raw = self.get_config_raw(doc_key)
        return dict(raw) if isinstance(raw, dict) else dict(default)

    def config_ready(self) -> bool:
        return all(self.has_config(k) for k in _CONFIG_LIST_KEYS) and self.has_config(
            "personal.preferences"
        )

    def _session_row_to_meta(self, row: tuple[Any, ...]) -> dict[str, Any]:
        tenant = current_tenant_id()
        if len(row) >= 7:
            sid, title, pinned, created_at, updated_at, meta_json, row_tenant = row[:7]
        else:
            sid, title, pinned, created_at, updated_at, meta_json = row[:6]
            row_tenant = tenant
        extra: dict[str, Any] = {}
        if meta_json:
            try:
                parsed = json.loads(meta_json)
                if isinstance(parsed, dict):
                    extra = parsed
            except json.JSONDecodeError:
                pass
        meta = {
            "id": sid,
            "title": title,
            "pinned": bool(pinned),
            "created_at": created_at,
            "updated_at": updated_at,
            "tenant_id": row_tenant,
            **extra,
        }
        return meta

    def _split_session_meta(self, meta: dict[str, Any]) -> tuple[dict[str, Any], str]:
        top = {k: meta[k] for k in _SESSION_COLS if k in meta}
        extra = {k: v for k, v in meta.items() if k not in _SESSION_COLS}
        return top, json.dumps(extra, ensure_ascii=False)

    def list_sessions(self) -> list[dict[str, Any]]:
        tenant = current_tenant_id()
        try:
            rows = self._conn.execute(
                """
                SELECT id, title, pinned, created_at, updated_at, meta_json, tenant_id
                FROM sessions
                WHERE tenant_id = ?
                ORDER BY pinned DESC, updated_at DESC
                """,
                (tenant,),
            ).fetchall()
        except Exception:
            rows = self._conn.execute(
                """
                SELECT id, title, pinned, created_at, updated_at, meta_json
                FROM sessions
                ORDER BY pinned DESC, updated_at DESC
                """
            ).fetchall()
        return [self._session_row_to_meta(r) for r in rows]

    def create_session(self, title: str = "新综述") -> dict[str, Any]:
        sid = uuid.uuid4().hex
        now = _utc_now()
        tenant = current_tenant_id()
        try:
            self._conn.execute(
                """
                INSERT INTO sessions
                    (id, title, pinned, created_at, updated_at, meta_json, tenant_id)
                VALUES (?, ?, 0, ?, ?, '{}', ?)
                """,
                (sid, title, now, now, tenant),
            )
        except Exception:
            self._conn.execute(
                """
                INSERT INTO sessions (id, title, pinned, created_at, updated_at, meta_json)
                VALUES (?, ?, 0, ?, ?, '{}')
                """,
                (sid, title, now, now),
            )
        return {
            "id": sid,
            "title": title,
            "created_at": now,
            "updated_at": now,
            "pinned": False,
            "tenant_id": tenant,
        }

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        tenant = current_tenant_id()
        try:
            row = self._conn.execute(
                """
                SELECT id, title, pinned, created_at, updated_at, meta_json, tenant_id
                FROM sessions WHERE id = ? AND tenant_id = ?
                """,
                (session_id, tenant),
            ).fetchone()
        except Exception:
            row = self._conn.execute(
                """
                SELECT id, title, pinned, created_at, updated_at, meta_json
                FROM sessions WHERE id = ?
                """,
                (session_id,),
            ).fetchone()
        if not row:
            return None
        return self._session_row_to_meta(row)

    def upsert_session_meta(self, meta: dict[str, Any]) -> None:
        sid = str(meta.get("id") or "")
        if not sid:
            return
        top, extra_json = self._split_session_meta(meta)
        tenant = str(top.get("tenant_id") or current_tenant_id())
        try:
            self._conn.execute(
                """
                INSERT INTO sessions
                    (id, title, pinned, created_at, updated_at, meta_json, tenant_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    pinned = excluded.pinned,
                    updated_at = excluded.updated_at,
                    meta_json = excluded.meta_json,
                    tenant_id = excluded.tenant_id
                """,
                (
                    sid,
                    str(top.get("title") or "新综述"),
                    1 if top.get("pinned") else 0,
                    str(top.get("created_at") or _utc_now()),
                    str(top.get("updated_at") or _utc_now()),
                    extra_json,
                    tenant,
                ),
            )
        except Exception:
            self._conn.execute(
                """
                INSERT INTO sessions (id, title, pinned, created_at, updated_at, meta_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    pinned = excluded.pinned,
                    updated_at = excluded.updated_at,
                    meta_json = excluded.meta_json
                """,
                (
                    sid,
                    str(top.get("title") or "新综述"),
                    1 if top.get("pinned") else 0,
                    str(top.get("created_at") or _utc_now()),
                    str(top.get("updated_at") or _utc_now()),
                    extra_json,
                ),
            )

    def delete_session(self, session_id: str) -> None:
        self._conn.execute(
            "DELETE FROM session_messages WHERE session_id = ?",
            (session_id,),
        )
        self._conn.execute(
            "DELETE FROM session_documents WHERE session_id = ?",
            (session_id,),
        )
        self._conn.execute(
            "DELETE FROM session_artifacts WHERE session_id = ?",
            (session_id,),
        )
        self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    def next_message_seq(self, session_id: str) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(MAX(seq), 0) FROM session_messages WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return int(row[0] if row else 0) + 1

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        meta: dict[str, Any] | None = None,
    ) -> None:
        seq = self.next_message_seq(session_id)
        ts = _utc_now()
        self._conn.execute(
            """
            INSERT INTO session_messages
                (session_id, seq, role, content, meta_json, ts)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                seq,
                role,
                content,
                json.dumps(meta, ensure_ascii=False) if meta else None,
                ts,
            ),
        )
        existing = self.get_session(session_id)
        if existing:
            existing["updated_at"] = ts
            self.upsert_session_meta(existing)

    def load_messages(self, session_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT role, content, meta_json, ts
            FROM session_messages
            WHERE session_id = ?
            ORDER BY seq ASC
            """,
            (session_id,),
        ).fetchall()
        msgs: list[dict[str, Any]] = []
        for role, content, meta_json, ts in rows[-limit:]:
            rec: dict[str, Any] = {
                "role": role,
                "content": content,
                "ts": ts,
            }
            if meta_json:
                try:
                    m = json.loads(meta_json)
                    if isinstance(m, dict):
                        rec["meta"] = m
                except json.JSONDecodeError:
                    pass
            msgs.append(rec)
        return msgs

    def save_session_document(
        self, session_id: str, doc_type: str, data: dict[str, Any]
    ) -> None:
        payload = dict(data)
        payload["updated_at"] = _utc_now()
        self._conn.execute(
            """
            INSERT INTO session_documents (session_id, doc_type, content_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id, doc_type) DO UPDATE SET
                content_json = excluded.content_json,
                updated_at = excluded.updated_at
            """,
            (
                session_id,
                doc_type,
                json.dumps(payload, ensure_ascii=False),
                payload["updated_at"],
            ),
        )

    def load_session_document(
        self, session_id: str, doc_type: str
    ) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT content_json FROM session_documents
            WHERE session_id = ? AND doc_type = ?
            """,
            (session_id, doc_type),
        ).fetchone()
        if not row:
            return None
        try:
            data = json.loads(row[0])
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None

    def save_artifact(
        self,
        session_id: str,
        *,
        kind: str,
        content: str,
        filename: str,
        artifact_id: str,
    ) -> None:
        now = _utc_now()
        self._conn.execute(
            "UPDATE session_artifacts SET is_latest = 0 WHERE session_id = ? AND kind = ?",
            (session_id, kind),
        )
        self._conn.execute(
            """
            INSERT INTO session_artifacts
                (id, session_id, kind, filename, content, is_latest, created_at)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(id) DO UPDATE SET
                content = excluded.content,
                filename = excluded.filename,
                is_latest = 1,
                created_at = excluded.created_at
            """,
            (artifact_id, session_id, kind, filename, content, now),
        )
        meta = self.get_session(session_id)
        if meta is not None:
            versions_key = f"{kind}_versions"
            versions = list(meta.get(versions_key) or [])
            versions.append(
                {"id": artifact_id, "filename": filename, "created_at": now}
            )
            meta[versions_key] = versions[-20:]
            meta["updated_at"] = now
            self.upsert_session_meta(meta)

    def get_latest_artifact(
        self, session_id: str, kind: str
    ) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT filename, content, created_at
            FROM session_artifacts
            WHERE session_id = ? AND kind = ? AND is_latest = 1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (session_id, kind),
        ).fetchone()
        if not row:
            return None
        filename, content, created_at = row
        return {
            "filename": filename or f"{kind}-latest.md",
            "content": content or "",
            "updated_at": created_at or _utc_now(),
        }

    def read_library_db(self) -> dict[str, Any]:
        meta_row = self._conn.execute(
            "SELECT version, next_display_index FROM library_meta WHERE id = 1"
        ).fetchone()
        version = int(meta_row[0]) if meta_row else 1
        next_idx = int(meta_row[1]) if meta_row else 0
        tenant = current_tenant_id()
        try:
            rows = self._conn.execute(
                """
                SELECT id, canonical_key, display_index, item_json
                FROM library_items
                WHERE tenant_id = ?
                ORDER BY display_index ASC
                """,
                (tenant,),
            ).fetchall()
        except Exception:
            rows = self._conn.execute(
                """
                SELECT id, canonical_key, display_index, item_json
                FROM library_items
                ORDER BY display_index ASC
                """
            ).fetchall()
        items: dict[str, Any] = {}
        keys: dict[str, str] = {}
        for iid, ckey, _disp, item_json in rows:
            try:
                item = json.loads(item_json)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict):
                continue
            items[iid] = item
            if ckey:
                keys[ckey] = iid
        return {
            "version": version,
            "next_display_index": next_idx,
            "items": items,
            "keys": keys,
        }

    def write_library_db(self, data: dict[str, Any]) -> None:
        version = int(data.get("version") or 1)
        next_idx = int(data.get("next_display_index") or 0)
        self._conn.execute(
            """
            UPDATE library_meta
            SET version = ?, next_display_index = ?, updated_at = ?
            WHERE id = 1
            """,
            (version, next_idx, _utc_now()),
        )
        items = data.get("items") if isinstance(data.get("items"), dict) else {}
        keys = data.get("keys") if isinstance(data.get("keys"), dict) else {}
        tenant = current_tenant_id()
        try:
            self._conn.execute(
                "DELETE FROM library_items WHERE tenant_id = ?",
                (tenant,),
            )
        except Exception:
            self._conn.execute("DELETE FROM library_items")
        for iid, item in items.items():
            if not isinstance(item, dict):
                continue
            ckey = keys.get(
                str(item.get("canonical_key") or ""),
                None,
            )
            if not ckey:
                for k, v in keys.items():
                    if v == iid:
                        ckey = k
                        break
            try:
                self._conn.execute(
                    """
                    INSERT INTO library_items
                        (id, canonical_key, display_index, item_json, updated_at, tenant_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        canonical_key = excluded.canonical_key,
                        display_index = excluded.display_index,
                        item_json = excluded.item_json,
                        updated_at = excluded.updated_at,
                        tenant_id = excluded.tenant_id
                    """,
                    (
                        iid,
                        ckey,
                        int(item.get("display_index") or 0),
                        json.dumps(item, ensure_ascii=False),
                        str(item.get("updated_at") or _utc_now()),
                        tenant,
                    ),
                )
            except Exception:
                self._conn.execute(
                    """
                    INSERT INTO library_items
                        (id, canonical_key, display_index, item_json, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        canonical_key = excluded.canonical_key,
                        display_index = excluded.display_index,
                        item_json = excluded.item_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        iid,
                        ckey,
                        int(item.get("display_index") or 0),
                        json.dumps(item, ensure_ascii=False),
                        str(item.get("updated_at") or _utc_now()),
                    ),
                )

    def delete_library_item(self, item_id: str) -> None:
        self._conn.execute("DELETE FROM library_items WHERE id = ?", (item_id,))

    def save_blob(self, path: str, content: bytes) -> None:
        self._conn.execute(
            """
            INSERT INTO blob_files (path, storage, content_blob, size_bytes, updated_at)
            VALUES (?, 'turso', ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                storage = excluded.storage,
                content_blob = excluded.content_blob,
                size_bytes = excluded.size_bytes,
                updated_at = excluded.updated_at
            """,
            (path, content, len(content), _utc_now()),
        )

    def read_blob(self, path: str) -> bytes | None:
        row = self._conn.execute(
            "SELECT content_blob FROM blob_files WHERE path = ?",
            (path,),
        ).fetchone()
        if not row or row[0] is None:
            return None
        data = row[0]
        return data if isinstance(data, bytes) else bytes(data)

    def list_blob_paths(self, prefix: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT path FROM blob_files WHERE path LIKE ? ORDER BY path",
            (prefix + "%",),
        ).fetchall()
        return [str(r[0]) for r in rows if r and r[0]]
