"""Turso SQL over HTTP client (no native libsql dependency)."""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any

import httpx

_PIPELINE_SUFFIX = "/v2/pipeline"
_TIMEOUT = 60.0


def libsql_url_to_https(database_url: str) -> str:
    url = database_url.strip()
    if url.startswith("libsql://"):
        url = "https://" + url[len("libsql://") :]
    elif url.startswith("https://"):
        pass
    elif url.startswith("http://"):
        pass
    else:
        url = "https://" + url
    return url.rstrip("/")


def pipeline_url(database_url: str) -> str:
    base = libsql_url_to_https(database_url)
    if base.endswith(_PIPELINE_SUFFIX):
        return base
    return base + _PIPELINE_SUFFIX


def _encode_arg(value: Any) -> dict[str, Any]:
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "integer", "value": "1" if value else "0"}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": str(value)}
    if isinstance(value, bytes):
        return {"type": "blob", "base64": base64.b64encode(value).decode("ascii")}
    return {"type": "text", "value": str(value)}


def _decode_cell(cell: dict[str, Any] | None) -> Any:
    if not cell:
        return None
    typ = cell.get("type")
    if typ == "null":
        return None
    if typ == "integer":
        return int(cell.get("value") or 0)
    if typ == "float":
        return float(cell.get("value") or 0)
    if typ == "blob":
        raw = cell.get("base64") or ""
        return base64.b64decode(raw) if raw else b""
    return cell.get("value")


@dataclass
class TursoCursor:
    rows: list[tuple[Any, ...]]

    def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self.rows)

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.rows[0] if self.rows else None


class TursoHttpConnection:
    """Minimal connection compatible with turso_db migration helpers."""

    def __init__(self, database_url: str, auth_token: str) -> None:
        self._url = pipeline_url(database_url)
        self._token = auth_token.strip()
        self._client = httpx.Client(timeout=_TIMEOUT)

    def close(self) -> None:
        self._client.close()

    def commit(self) -> None:
        """HTTP pipeline auto-commits each statement outside explicit transactions."""

    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> TursoCursor:
        stmt: dict[str, Any] = {"sql": sql}
        if params:
            stmt["args"] = [_encode_arg(p) for p in params]
        payload = {
            "requests": [
                {"type": "execute", "stmt": stmt},
                {"type": "close"},
            ]
        }
        headers = {"Authorization": f"Bearer {self._token}"}
        resp = self._client.post(self._url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        rows: list[tuple[Any, ...]] = []
        for item in data.get("results") or []:
            if item.get("type") == "error":
                err = item.get("error") or item
                raise RuntimeError(f"Turso SQL error: {err}")
            if item.get("type") != "ok":
                continue
            response = item.get("response") or {}
            if response.get("type") != "execute":
                continue
            result = response.get("result") or {}
            for row in result.get("rows") or []:
                rows.append(tuple(_decode_cell(cell) for cell in row))
        return TursoCursor(rows=rows)

    def execute_many(self, statements: list[str]) -> None:
        """Run multiple DDL/DML in one pipeline (migration)."""
        requests: list[dict[str, Any]] = [
            {"type": "execute", "stmt": {"sql": sql}} for sql in statements if sql.strip()
        ]
        requests.append({"type": "close"})
        headers = {"Authorization": f"Bearer {self._token}"}
        resp = self._client.post(self._url, headers=headers, json={"requests": requests})
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("results") or []:
            if item.get("type") == "error":
                raise RuntimeError(f"Turso SQL error: {item.get('error') or item}")


def get_connection() -> TursoHttpConnection:
    from app.storage.storage_settings import resolve_turso_credentials

    url, token = resolve_turso_credentials()
    if not url:
        raise RuntimeError("TURSO_DATABASE_URL is not set")
    return TursoHttpConnection(url, token)
