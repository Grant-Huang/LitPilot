"""File-based persistence — no database."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from filelock import FileLock

from app.core.config import DATA_DIR


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


_DEFAULT_SESSION_TITLES = frozenset({"新综述", "新对话", "未命名"})


def is_default_session_title(title: str) -> bool:
    t = (title or "").strip()
    return not t or t in _DEFAULT_SESSION_TITLES


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    lock_path = path.with_suffix(path.suffix + ".lock")
    with FileLock(str(lock_path)):
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)


class FileStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or DATA_DIR).resolve()
        self._ensure_layout()

    def _ensure_layout(self) -> None:
        for sub in (
            "config",
            "sessions",
            "refs",
            "sources",
            "pdfs",
            "artifacts",
            "cache/tavily",
        ):
            (self.root / sub).mkdir(parents=True, exist_ok=True)
        idx = self.root / "sessions" / "index.json"
        if not idx.is_file():
            _write_json_atomic(idx, {"sessions": []})
        ref_list = self.root / "refs" / "ref-list.txt"
        if not ref_list.is_file():
            ref_list.write_text("", encoding="utf-8")
        ref_idx = self.root / "refs" / "index.json"
        if not ref_idx.is_file():
            _write_json_atomic(ref_idx, {"refs": []})

    @property
    def agent_config_path(self) -> Path:
        return self.root / "config" / "agent.json"

    def load_agent_settings(self) -> dict[str, Any]:
        data = _read_json(self.agent_config_path, {})
        if not isinstance(data, dict):
            return {}
        return data

    def save_agent_settings(self, partial: dict[str, Any]) -> dict[str, Any]:
        current = self.load_agent_settings()
        for k, v in partial.items():
            if v is None:
                continue
            if isinstance(v, str) and v.startswith("***"):
                continue
            current[k] = v
        _write_json_atomic(self.agent_config_path, current)
        return self.get_agent_settings_merged()

    def get_agent_settings_merged(self) -> dict[str, Any]:
        """Merge file config with environment variables for secrets."""
        import os

        cfg = self.load_agent_settings()
        env_map = {
            "tavily_api_key": os.getenv("TAVILY_API_KEY", ""),
            "jina_api_key": os.getenv("JINA_API_KEY", ""),
            "llm_provider": os.getenv("LLM_PROVIDER", "openai"),
            "llm_api_key": os.getenv("OPENAI_API_KEY", ""),
            "llm_model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            "llm_base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        }
        merged = {
            "tavily_api_key": cfg.get("tavily_api_key") or env_map["tavily_api_key"],
            "jina_api_key": cfg.get("jina_api_key") or env_map["jina_api_key"],
            "llm_provider": cfg.get("llm_provider") or env_map["llm_provider"],
            "llm_api_key": cfg.get("llm_api_key") or env_map["llm_api_key"],
            "llm_model": cfg.get("llm_model") or env_map["llm_model"],
            "llm_base_url": cfg.get("llm_base_url") or env_map["llm_base_url"],
            "llm_group_id": cfg.get("llm_group_id") or os.getenv("MINIMAX_GROUP_ID", ""),
            "fetch_parallel": int(cfg.get("fetch_parallel") or 3),
            "fetch_timeout_sec": float(cfg.get("fetch_timeout_sec") or 45),
            "tavily_max_results": int(cfg.get("tavily_max_results") or 8),
            "max_fetch_urls": int(cfg.get("max_fetch_urls") or 5),
            "literature_source_mode": (cfg.get("literature_source_mode") or "merge"),
            "tavily_retry_count": int(cfg.get("tavily_retry_count") or 0),
            "fetch_retry_count": int(cfg.get("fetch_retry_count") or 0),
            "fetch_retry_delay_ms": int(cfg.get("fetch_retry_delay_ms") or 500),
            "plan_confirm": bool(cfg.get("plan_confirm", False)),
            "citation_format": (cfg.get("citation_format") or "apa").strip().lower(),
            "use_llm_planner": bool(cfg.get("use_llm_planner", True)),
            "think_mode": (cfg.get("think_mode") or "lite").strip().lower(),
            "think_use_reasoning": bool(cfg.get("think_use_reasoning", False)),
            "think_model": (cfg.get("think_model") or "").strip(),
            "think_max_tokens_per_phase": int(cfg.get("think_max_tokens_per_phase") or 280),
        }
        return merged

    def list_sessions(self) -> list[dict[str, Any]]:
        idx = _read_json(self.root / "sessions" / "index.json", {"sessions": []})
        sessions = idx.get("sessions") or []
        enriched: list[dict[str, Any]] = []
        for s in sessions:
            sid = s.get("id")
            if not sid:
                continue
            meta = self.get_session(str(sid)) or s
            enriched.append(
                {
                    "id": sid,
                    "title": meta.get("title") or s.get("title") or "新综述",
                    "created_at": meta.get("created_at") or s.get("created_at"),
                    "updated_at": meta.get("updated_at") or s.get("updated_at"),
                    "pinned": bool(meta.get("pinned", False)),
                }
            )
        enriched.sort(
            key=lambda s: (
                -int(bool(s.get("pinned"))),
                s.get("updated_at") or "",
            ),
            reverse=True,
        )
        return enriched

    def create_session(self, title: str = "新综述") -> dict[str, Any]:
        sid = uuid.uuid4().hex
        now = _utc_now()
        meta = {
            "id": sid,
            "title": title,
            "created_at": now,
            "updated_at": now,
            "pinned": False,
        }
        sess_dir = self.root / "sessions" / sid
        sess_dir.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(sess_dir / "meta.json", meta)
        idx_path = self.root / "sessions" / "index.json"
        lock_path = idx_path.with_suffix(".lock")
        with FileLock(str(lock_path)):
            idx = _read_json(idx_path, {"sessions": []})
            sessions = idx.get("sessions") or []
            sessions.insert(
                0,
                {"id": sid, "title": title, "updated_at": now, "pinned": False},
            )
            _write_json_atomic(idx_path, {"sessions": sessions})
        return meta

    def get_session(self, session_id: str) -> Optional[dict[str, Any]]:
        meta_path = self.root / "sessions" / session_id / "meta.json"
        if not meta_path.is_file():
            return None
        return _read_json(meta_path, None)

    def update_session(
        self,
        session_id: str,
        *,
        title: str | None = None,
        pinned: bool | None = None,
    ) -> Optional[dict[str, Any]]:
        meta = self.get_session(session_id)
        if not meta:
            return None
        now = _utc_now()
        if title is not None:
            meta["title"] = title
        if pinned is not None:
            meta["pinned"] = pinned
        meta["updated_at"] = now
        _write_json_atomic(self.root / "sessions" / session_id / "meta.json", meta)
        idx_path = self.root / "sessions" / "index.json"
        lock_path = idx_path.with_suffix(".lock")
        with FileLock(str(lock_path)):
            idx = _read_json(idx_path, {"sessions": []})
            for s in idx.get("sessions") or []:
                if s.get("id") == session_id:
                    if title is not None:
                        s["title"] = title
                    if pinned is not None:
                        s["pinned"] = pinned
                    s["updated_at"] = now
            _write_json_atomic(idx_path, idx)
        return meta

    def delete_session(self, session_id: str) -> bool:
        import shutil

        sess_dir = self.root / "sessions" / session_id
        if sess_dir.is_dir():
            shutil.rmtree(sess_dir)
        art_dir = self.root / "artifacts" / session_id
        if art_dir.is_dir():
            shutil.rmtree(art_dir)
        idx_path = self.root / "sessions" / "index.json"
        lock_path = idx_path.with_suffix(".lock")
        with FileLock(str(lock_path)):
            idx = _read_json(idx_path, {"sessions": []})
            sessions = [s for s in (idx.get("sessions") or []) if s.get("id") != session_id]
            _write_json_atomic(idx_path, {"sessions": sessions})
        return True

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        meta: dict[str, Any] | None = None,
    ) -> None:
        msg_path = self.root / "sessions" / session_id / "messages.jsonl"
        msg_path.parent.mkdir(parents=True, exist_ok=True)
        rec: dict[str, Any] = {
            "role": role,
            "content": content,
            "ts": _utc_now(),
        }
        if meta:
            rec["meta"] = meta
        line = json.dumps(rec, ensure_ascii=False)
        with open(msg_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        meta = self.get_session(session_id)
        if meta:
            meta["updated_at"] = _utc_now()
            _write_json_atomic(
                self.root / "sessions" / session_id / "meta.json",
                meta,
            )
            idx_path = self.root / "sessions" / "index.json"
            lock_path = idx_path.with_suffix(".lock")
            with FileLock(str(lock_path)):
                idx = _read_json(idx_path, {"sessions": []})
                for s in idx.get("sessions") or []:
                    if s.get("id") == session_id:
                        s["updated_at"] = meta["updated_at"]
                _write_json_atomic(idx_path, idx)

    def load_messages(
        self,
        session_id: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        msg_path = self.root / "sessions" / session_id / "messages.jsonl"
        if not msg_path.is_file():
            return []
        lines = msg_path.read_text(encoding="utf-8").strip().splitlines()
        msgs = []
        for ln in lines[-limit:]:
            if ln.strip():
                try:
                    msgs.append(json.loads(ln))
                except json.JSONDecodeError:
                    continue
        return msgs

    def save_review_artifact(
        self,
        session_id: str,
        content: str,
    ) -> Path:
        art_dir = self.root / "artifacts" / session_id
        art_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        path = art_dir / f"review-{ts}.md"
        path.write_text(content, encoding="utf-8")
        latest = art_dir / "review-latest.md"
        latest.write_text(content, encoding="utf-8")
        return path

    def get_latest_review(self, session_id: str) -> dict[str, Any] | None:
        art_dir = self.root / "artifacts" / session_id
        latest = art_dir / "review-latest.md"
        if latest.is_file():
            return {
                "filename": "review-latest.md",
                "content": latest.read_text(encoding="utf-8"),
                "updated_at": datetime.fromtimestamp(
                    latest.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
            }
        if not art_dir.is_dir():
            return None
        files = sorted(art_dir.glob("review-*.md"), key=lambda p: p.stat().st_mtime)
        if not files:
            return None
        path = files[-1]
        return {
            "filename": path.name,
            "content": path.read_text(encoding="utf-8"),
            "updated_at": datetime.fromtimestamp(
                path.stat().st_mtime, tz=timezone.utc
            ).isoformat(),
        }

    def append_ref_line(self, line: str) -> None:
        ref_path = self.root / "refs" / "ref-list.txt"
        lock_path = ref_path.with_suffix(".lock")
        with FileLock(str(lock_path)):
            with open(ref_path, "a", encoding="utf-8") as f:
                f.write(line.rstrip() + "\n\n")

    def read_ref_list(self) -> str:
        ref_path = self.root / "refs" / "ref-list.txt"
        if not ref_path.is_file():
            return ""
        return ref_path.read_text(encoding="utf-8")

    def load_ref_index(self) -> dict[str, Any]:
        return _read_json(self.root / "refs" / "index.json", {"refs": []})

    def append_ref_index(self, entry: dict[str, Any]) -> dict[str, Any]:
        idx_path = self.root / "refs" / "index.json"
        lock_path = idx_path.with_suffix(".lock")
        with FileLock(str(lock_path)):
            idx = _read_json(idx_path, {"refs": []})
            refs = idx.get("refs") or []
            refs.append(entry)
            _write_json_atomic(idx_path, {"refs": refs})
        return entry

    def list_pdfs(self) -> list[str]:
        pdf_dir = self.root / "pdfs"
        if not pdf_dir.is_dir():
            return []
        return sorted(f.name for f in pdf_dir.iterdir() if f.suffix.lower() == ".pdf")

    def pdf_path(self, filename: str) -> Path:
        safe = Path(filename).name
        return self.root / "pdfs" / safe


_store: FileStore | None = None


def get_store() -> FileStore:
    global _store
    if _store is None:
        _store = FileStore()
    return _store
