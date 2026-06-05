"""Turso-backed FileStore (P1–P5)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.storage.file_store import FileStore, _utc_now
from app.storage.turso_db import apply_migrations
from app.storage.turso_repo import TursoRepo, current_tenant_id

# All phases implemented
TURSO_PHASE = 5

_PATH_TO_DOC_KEY: dict[str, str] = {
    "system.credentials.json": "system.credentials",
    "system.instances.json": "system.instances",
    "system.capabilities.json": "system.capabilities",
    "personal.preferences.json": "personal.preferences",
    "agent.json": "agent.legacy",
    "system.storage.json": "system.storage",
    "library.json": "refs.library.legacy",
    "ref-list.txt": "refs.ref_list",
    "index.json": "refs.index",
}


class TursoStore(FileStore):
    """Persist sessions, config, and library in Turso; blobs hybrid local + DB."""

    def __init__(self, root: Path | None = None) -> None:
        apply_migrations()
        self._repo = TursoRepo()
        super().__init__(root=root)

    def _doc_key_for_path(self, path: Path) -> str | None:
        return _PATH_TO_DOC_KEY.get(path.name)

    def _config_path_exists(self, path: Path) -> bool:
        key = self._doc_key_for_path(path)
        if key:
            return self._repo.has_config(key)
        return path.is_file()

    def _write_config_json(self, path: Path, data: Any) -> None:
        key = self._doc_key_for_path(path)
        if key:
            self._repo.set_config_raw(key, data)
            return
        from app.storage.file_store import _write_json_atomic

        _write_json_atomic(path, data)

    def _load_config_list(self, path: Path) -> list[dict[str, Any]]:
        key = self._doc_key_for_path(path)
        if key:
            return self._repo.get_config_list(key)
        return super()._load_config_list(path)

    def _save_config_list(self, path: Path, items: list[dict[str, Any]]) -> None:
        key = self._doc_key_for_path(path)
        if key:
            self._repo.set_config_list(key, items)
            return
        super()._save_config_list(path, items)

    def _load_config_obj(self, path: Path, default: dict[str, Any]) -> dict[str, Any]:
        key = self._doc_key_for_path(path)
        if key:
            return self._repo.get_config_obj(key, default)
        return super()._load_config_obj(path, default)

    def ensure_settings_v2_migrated(self) -> None:
        creds_exists = self._config_path_exists(self.system_credentials_path)
        inst_exists = self._config_path_exists(self.system_instances_path)
        caps_exists = self._config_path_exists(self.system_capabilities_path)
        prefs_exists = self._config_path_exists(self.personal_preferences_path)
        if creds_exists and inst_exists and caps_exists and prefs_exists:
            self._ensure_capability_param_defaults()
            self._ensure_default_instances()
            self._ensure_deploy_catalog()
            return
        super().ensure_settings_v2_migrated()

    def save_personal_preferences(self, partial: dict[str, Any]) -> dict[str, Any]:
        self.ensure_settings_v2_migrated()
        current = self._load_config_obj(self.personal_preferences_path, {"preferences": {}})
        prefs = current.get("preferences") if isinstance(current.get("preferences"), dict) else {}
        for k, v in partial.items():
            if v is None:
                continue
            prefs[k] = v
        out = dict(current)
        out["preferences"] = prefs
        out["updated_at"] = _utc_now()
        self._write_config_json(self.personal_preferences_path, out)
        return self.get_personal_preferences()

    def list_sessions(self) -> list[dict[str, Any]]:
        return self._repo.list_sessions()

    def create_session(self, title: str = "新综述") -> dict[str, Any]:
        return self._repo.create_session(title=title)

    def get_session(self, session_id: str) -> Optional[dict[str, Any]]:
        return self._repo.get_session(session_id)

    def update_session(
        self,
        session_id: str,
        *,
        title: str | None = None,
        pinned: bool | None = None,
        title_auto_set: bool | None = None,
    ) -> Optional[dict[str, Any]]:
        meta = self.get_session(session_id)
        if not meta:
            return None
        if title is not None:
            meta["title"] = title
        if pinned is not None:
            meta["pinned"] = pinned
        if title_auto_set is not None:
            meta["title_auto_set"] = title_auto_set
        meta["updated_at"] = _utc_now()
        self._repo.upsert_session_meta(meta)
        return meta

    def patch_session_meta(
        self,
        session_id: str,
        patch: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        meta = self.get_session(session_id)
        if not meta:
            return None
        for key, value in patch.items():
            if value is not None:
                meta[key] = value
        meta["updated_at"] = _utc_now()
        self._repo.upsert_session_meta(meta)
        return meta

    def save_corpus(self, session_id: str, data: dict[str, Any]) -> None:
        self._repo.save_session_document(session_id, "corpus", data)

    def load_corpus(self, session_id: str) -> dict[str, Any] | None:
        return self._repo.load_session_document(session_id, "corpus")

    def save_outline(self, session_id: str, data: dict[str, Any]) -> None:
        self._repo.save_session_document(session_id, "outline", data)

    def load_outline(self, session_id: str) -> dict[str, Any] | None:
        return self._repo.load_session_document(session_id, "outline")

    def has_corpus(self, session_id: str) -> bool:
        return self.load_corpus(session_id) is not None

    def delete_session(self, session_id: str) -> bool:
        if not self.get_session(session_id):
            return False
        self._repo.delete_session(session_id)
        return True

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        meta: dict[str, Any] | None = None,
    ) -> None:
        self._repo.append_message(session_id, role, content, meta=meta)

    def load_messages(
        self,
        session_id: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        return self._repo.load_messages(session_id, limit=limit)

    def load_first_user_message(self, session_id: str, *, max_chars: int = 800) -> str:
        for rec in self._repo.load_messages(session_id, limit=10_000):
            if rec.get("role") != "user":
                continue
            content = rec.get("content") or ""
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(str(block.get("text") or ""))
                    elif isinstance(block, str):
                        parts.append(block)
                content = "\n".join(parts)
            text = str(content).strip()
            if text:
                return text[:max_chars]
        return ""

    def _save_markdown_artifact(
        self,
        session_id: str,
        content: str,
        *,
        kind: str,
        meta_key: str,
    ) -> tuple[Path, str]:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        version_id = f"{kind}_{uuid.uuid4().hex[:12]}"
        filename = f"{kind}-{ts}.md"
        self._repo.save_artifact(
            session_id,
            kind=kind,
            content=content,
            filename=filename,
            artifact_id=version_id,
        )
        art_dir = self.root / "artifacts" / session_id
        art_dir.mkdir(parents=True, exist_ok=True)
        path = art_dir / filename
        path.write_text(content, encoding="utf-8")
        return path, version_id

    def get_latest_review(self, session_id: str) -> dict[str, Any] | None:
        return self._repo.get_latest_artifact(session_id, "review")

    def get_latest_matrix(self, session_id: str) -> dict[str, Any] | None:
        return self._repo.get_latest_artifact(session_id, "matrix")

    def read_library_db(self) -> dict[str, Any]:
        return self._repo.read_library_db()

    def write_library_db(self, data: dict[str, Any]) -> None:
        self._repo.write_library_db(data)

    def library_delete_item_files(self, item_id: str) -> None:
        self._repo.delete_library_item(item_id)
        src = self.root / "sources" / f"{item_id}.md"
        if src.is_file():
            src.unlink()

    def read_source_text(self, item_id: str) -> str:
        blob = self._repo.read_blob(f"sources/{item_id}.md")
        if blob:
            return blob.decode("utf-8", errors="replace")
        path = self.root / "sources" / f"{item_id}.md"
        if path.is_file():
            return path.read_text(encoding="utf-8")
        return ""

    def write_source_text(self, item_id: str, text: str) -> None:
        body = (text or "").strip()
        if not body:
            return
        clipped = body[:500_000]
        path = self.root / "sources" / f"{item_id}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(clipped, encoding="utf-8")
        self._repo.save_blob(f"sources/{item_id}.md", clipped.encode("utf-8"))

    def append_ref_line(self, line: str) -> None:
        current = self._repo.get_config_raw("refs.ref_list") or ""
        if not isinstance(current, str):
            current = str(current)
        current = current + line.rstrip() + "\n\n"
        self._repo.set_config_raw("refs.ref_list", current)

    def read_ref_list(self) -> str:
        raw = self._repo.get_config_raw("refs.ref_list")
        return str(raw) if isinstance(raw, str) else ""

    def load_ref_index(self) -> dict[str, Any]:
        raw = self._repo.get_config_raw("refs.index")
        if isinstance(raw, dict):
            return raw
        return {"refs": []}

    def append_ref_index(self, entry: dict[str, Any]) -> dict[str, Any]:
        idx = self.load_ref_index()
        refs = idx.get("refs") or []
        refs.append(entry)
        idx["refs"] = refs
        self._repo.set_config_raw("refs.index", idx)
        return entry

    def list_pdfs(self) -> list[str]:
        names = [
            p.replace("pdfs/", "")
            for p in self._repo.list_blob_paths("pdfs/")
            if p.endswith(".pdf")
        ]
        pdf_dir = self.root / "pdfs"
        if pdf_dir.is_dir():
            for f in pdf_dir.iterdir():
                if f.suffix.lower() == ".pdf" and f.name not in names:
                    names.append(f.name)
        return sorted(names)

    def pdf_path(self, filename: str) -> Path:
        safe = Path(filename).name
        path = self.root / "pdfs" / safe
        if path.is_file():
            return path
        blob = self._repo.read_blob(f"pdfs/{safe}")
        if blob:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(blob)
        return path

    def save_pdf_bytes(self, filename: str, content: bytes) -> Path:
        safe = Path(filename).name
        path = self.root / "pdfs" / safe
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        self._repo.save_blob(f"pdfs/{safe}", content)
        return path

    def tenant_id(self) -> str:
        return current_tenant_id()

    def get_storage_settings(self) -> dict[str, Any]:
        return self._repo.get_config_obj("system.storage", {})

    def save_storage_settings(self, partial: dict[str, Any]) -> dict[str, Any]:
        current = self.get_storage_settings()
        for key, value in partial.items():
            if value is None:
                continue
            if key == "auth_token" and str(value).startswith("***"):
                continue
            if key == "auth_token" and not str(value).strip():
                current.pop("auth_token", None)
                continue
            current[key] = value
        current["updated_at"] = _utc_now()
        self._repo.set_config_raw("system.storage", current)
        url, token = resolve_turso_credentials_merged(current)
        if url:
            from app.storage.storage_settings import set_runtime_turso_credentials

            set_runtime_turso_credentials(url, token)
        return self.get_storage_settings_public()

    def get_storage_settings_public(self) -> dict[str, Any]:
        from app.storage.storage_settings import build_storage_status

        return build_storage_status(self)


def resolve_turso_credentials_merged(admin: dict[str, Any]) -> tuple[str, str]:
    import os

    env_url = os.getenv("TURSO_DATABASE_URL", "").strip()
    env_token = os.getenv("TURSO_AUTH_TOKEN", "").strip()
    url = str(admin.get("database_url") or "").strip() or env_url
    token = str(admin.get("auth_token") or "").strip() or env_token
    return url, token
