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
from app.agents.tools.tavily_search import ACADEMIC_SEARCH_DOMAINS, DEFAULT_EXCLUDE_DOMAINS


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

    # --- v2 settings layout (system/personal split) ---
    @property
    def system_credentials_path(self) -> Path:
        return self.root / "config" / "system.credentials.json"

    @property
    def system_instances_path(self) -> Path:
        return self.root / "config" / "system.instances.json"

    @property
    def system_capabilities_path(self) -> Path:
        return self.root / "config" / "system.capabilities.json"

    @property
    def personal_preferences_path(self) -> Path:
        return self.root / "config" / "personal.preferences.json"

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
        """Merge v2 system/personal config with environment variables for secrets."""
        import os

        from app.storage.runtime_settings import build_runtime_settings

        self.ensure_settings_v2_migrated()
        runtime = build_runtime_settings(
            credentials=self.list_system_credentials(),
            instances=self.list_system_instances(),
            capabilities=self.list_system_capabilities(),
            personal=self.get_personal_preferences(),
        )
        env_map = {
            "tavily_api_key": os.getenv("TAVILY_API_KEY", ""),
            "jina_api_key": os.getenv("JINA_API_KEY", ""),
            "llm_provider": os.getenv("LLM_PROVIDER", "openai"),
            "llm_api_key": os.getenv("OPENAI_API_KEY", ""),
            "llm_model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            "llm_base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            "llm_group_id": os.getenv("MINIMAX_GROUP_ID", ""),
        }
        merged = dict(runtime)
        if not merged.get("tavily_api_key"):
            merged["tavily_api_key"] = env_map["tavily_api_key"]
        if not merged.get("jina_api_key"):
            merged["jina_api_key"] = env_map["jina_api_key"]
        if not merged.get("llm_api_key"):
            merged["llm_api_key"] = env_map["llm_api_key"]
        if not merged.get("llm_provider"):
            merged["llm_provider"] = env_map["llm_provider"]
        if not merged.get("llm_model"):
            merged["llm_model"] = env_map["llm_model"]
        if not merged.get("llm_base_url"):
            merged["llm_base_url"] = env_map["llm_base_url"]
        if not merged.get("llm_group_id"):
            merged["llm_group_id"] = env_map["llm_group_id"]
        return merged

    def _legacy_agent_settings_merged(self) -> dict[str, Any]:
        """Read legacy agent.json merged with env (migration source only)."""
        import os

        cfg = self.load_agent_settings()
        return {
            "tavily_api_key": cfg.get("tavily_api_key") or os.getenv("TAVILY_API_KEY", ""),
            "jina_api_key": cfg.get("jina_api_key") or os.getenv("JINA_API_KEY", ""),
            "llm_provider": cfg.get("llm_provider") or os.getenv("LLM_PROVIDER", "openai"),
            "llm_api_key": cfg.get("llm_api_key") or os.getenv("OPENAI_API_KEY", ""),
            "llm_model": cfg.get("llm_model") or os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            "llm_base_url": cfg.get("llm_base_url") or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            "llm_group_id": cfg.get("llm_group_id") or os.getenv("MINIMAX_GROUP_ID", ""),
            "fetch_parallel": int(cfg.get("fetch_parallel") or 3),
            "fetch_timeout_sec": float(cfg.get("fetch_timeout_sec") or 45),
            "tavily_max_results": int(cfg.get("tavily_max_results") or 8),
            "max_fetch_urls": int(cfg.get("max_fetch_urls") or 5),
            "literature_source_mode": (cfg.get("literature_source_mode") or "merge"),
            "tavily_retry_count": int(cfg.get("tavily_retry_count") or 0),
            "fetch_retry_count": int(cfg.get("fetch_retry_count") or 0),
            "fetch_retry_delay_ms": int(cfg.get("fetch_retry_delay_ms") or 500),
            "max_source_chars": int(cfg.get("max_source_chars") or 14_000),
            "plan_confirm": bool(cfg.get("plan_confirm", False)),
            "citation_format": (cfg.get("citation_format") or "apa").strip().lower(),
            "use_llm_planner": bool(cfg.get("use_llm_planner", True)),
            "orchestrator_mode": (cfg.get("orchestrator_mode") or "lite").strip().lower(),
            "orchestrator_use_reasoning": bool(cfg.get("orchestrator_use_reasoning", False)),
            "orchestrator_model": (cfg.get("orchestrator_model") or "").strip(),
            "orchestrator_max_tokens_per_phase": int(
                cfg.get("orchestrator_max_tokens_per_phase") or 280
            ),
            "review_system_prompt_template": str(cfg.get("review_system_prompt_template") or ""),
        }

    # --- v2 settings helpers ---
    def _load_config_list(self, path: Path) -> list[dict[str, Any]]:
        data = _read_json(path, {"items": []})
        if not isinstance(data, dict):
            return []
        items = data.get("items") or []
        if not isinstance(items, list):
            return []
        out: list[dict[str, Any]] = []
        for it in items:
            if isinstance(it, dict):
                out.append(it)
        return out

    def _save_config_list(self, path: Path, items: list[dict[str, Any]]) -> None:
        _write_json_atomic(path, {"items": items, "updated_at": _utc_now()})

    def _load_config_obj(self, path: Path, default: dict[str, Any]) -> dict[str, Any]:
        data = _read_json(path, default)
        if not isinstance(data, dict):
            return dict(default)
        return data

    def ensure_settings_v2_migrated(self) -> None:
        """
        One-time migration to v2 settings layout.

        Creates:
        - config/system.credentials.json
        - config/system.instances.json
        - config/system.capabilities.json
        - config/personal.preferences.json

        Data source: merged legacy agent settings (agent.json + env).
        """
        creds_exists = self.system_credentials_path.is_file()
        inst_exists = self.system_instances_path.is_file()
        caps_exists = self.system_capabilities_path.is_file()
        prefs_exists = self.personal_preferences_path.is_file()
        if creds_exists and inst_exists and caps_exists and prefs_exists:
            self._ensure_capability_param_defaults()
            return

        legacy = self._legacy_agent_settings_merged()
        now = _utc_now()

        # credentials
        credentials: list[dict[str, Any]] = []
        cred_by_key: dict[str, str] = {}

        def add_cred(*, key: str, type_: str, name: str, secret: str, extra: dict[str, Any] | None = None) -> None:
            if key in cred_by_key:
                return
            cid = uuid.uuid4().hex
            cred_by_key[key] = cid
            item: dict[str, Any] = {
                "id": cid,
                "type": type_,
                "name": name,
                "has_secret": bool(secret),
                "secret": secret,
                "created_at": now,
                "updated_at": now,
                "status": "unknown",
                "last_verified_at": None,
            }
            if extra:
                item.update(extra)
            credentials.append(item)

        add_cred(
            key="tavily",
            type_="tavily",
            name="Tavily · default",
            secret=str(legacy.get("tavily_api_key") or ""),
        )
        add_cred(
            key="jina",
            type_="jina",
            name="Jina · default",
            secret=str(legacy.get("jina_api_key") or ""),
        )
        llm_provider = str(legacy.get("llm_provider") or "openai")
        add_cred(
            key="llm_primary",
            type_=f"llm:{llm_provider}",
            name=f"LLM · {llm_provider} · primary",
            secret=str(legacy.get("llm_api_key") or ""),
            extra={
                "base_url": str(legacy.get("llm_base_url") or ""),
                "group_id": str(legacy.get("llm_group_id") or ""),
            },
        )

        if not creds_exists:
            self._save_config_list(self.system_credentials_path, credentials)

        # instances
        instances: list[dict[str, Any]] = []
        inst_by_key: dict[str, str] = {}

        def add_instance(*, key: str, name: str, provider: str, credential_id: str, model_name: str, default_params: dict[str, Any] | None = None) -> None:
            if key in inst_by_key:
                return
            iid = uuid.uuid4().hex
            inst_by_key[key] = iid
            instances.append(
                {
                    "id": iid,
                    "name": name,
                    "provider": provider,
                    "credential_id": credential_id,
                    "model_name": model_name,
                    "default_params": default_params or {},
                    "created_at": now,
                    "updated_at": now,
                    "status": "unknown",
                    "last_verified_at": None,
                }
            )

        primary_cred_id = cred_by_key.get("llm_primary") or ""
        primary_model = str(legacy.get("llm_model") or "").strip() or "gpt-4o-mini"
        add_instance(
            key="review_main",
            name="review-main",
            provider=llm_provider,
            credential_id=primary_cred_id,
            model_name=primary_model,
        )
        orch_model = str(legacy.get("orchestrator_model") or "").strip()
        if orch_model:
            add_instance(
                key="orchestrator",
                name="orchestrator",
                provider=llm_provider,
                credential_id=primary_cred_id,
                model_name=orch_model,
            )

        if not inst_exists:
            self._save_config_list(self.system_instances_path, instances)

        # capabilities (bindings + system params)
        capabilities: list[dict[str, Any]] = []

        def cap(
            capability_id: str,
            label: str,
            *,
            primary_ref: dict[str, Any] | None,
            override_params: dict[str, Any] | None = None,
            params: dict[str, Any] | None = None,
            enabled: bool = True,
        ) -> None:
            capabilities.append(
                {
                    "capability_id": capability_id,
                    "label": label,
                    "enabled": enabled,
                    "primary_ref": primary_ref,
                    "override_params": override_params or {},
                    "params": params or {},
                    "created_at": now,
                    "updated_at": now,
                }
            )

        cap(
            "review_main",
            "文献综述生成",
            primary_ref={"kind": "instance", "id": inst_by_key.get("review_main")},
        )
        cap(
            "orchestrator",
            "编排与解说",
            primary_ref={
                "kind": "instance",
                "id": inst_by_key.get("orchestrator") or inst_by_key.get("review_main"),
            },
            params={
                "use_llm_planner": bool(legacy.get("use_llm_planner", True)),
                "orchestrator_mode": str(legacy.get("orchestrator_mode") or "lite"),
                "orchestrator_use_reasoning": bool(legacy.get("orchestrator_use_reasoning", False)),
                "orchestrator_max_tokens_per_phase": int(
                    legacy.get("orchestrator_max_tokens_per_phase") or 280
                ),
            },
        )
        cap(
            "web_search",
            "web_search · Tavily 检索",
            primary_ref={"kind": "credential", "id": cred_by_key.get("tavily")},
            params={
                "tavily_max_results": int(legacy.get("tavily_max_results") or 8),
                "tavily_retry_count": int(legacy.get("tavily_retry_count") or 0),
                "include_domains": list(ACADEMIC_SEARCH_DOMAINS),
                "exclude_domains": list(DEFAULT_EXCLUDE_DOMAINS),
                "search_depth": "advanced",
                "enforce_domain_filter": True,
                "enable_junk_filter": True,
            },
        )
        cap(
            "web_fetch",
            "web_fetch · Jina 抓取",
            primary_ref={"kind": "credential", "id": cred_by_key.get("jina")},
            params={
                "max_fetch_urls": int(legacy.get("max_fetch_urls") or 5),
                "fetch_parallel": int(legacy.get("fetch_parallel") or 3),
                "fetch_timeout_sec": float(legacy.get("fetch_timeout_sec") or 45),
                "fetch_retry_count": int(legacy.get("fetch_retry_count") or 0),
                "fetch_retry_delay_ms": int(legacy.get("fetch_retry_delay_ms") or 500),
                "max_source_chars": int(legacy.get("max_source_chars") or 14_000),
            },
        )
        cap(
            "literature_source",
            "文献来源策略",
            primary_ref=None,
            params={"literature_source_mode": str(legacy.get("literature_source_mode") or "merge")},
        )
        cap(
            "prompts",
            "提示词模板",
            primary_ref=None,
            params={"review_system_prompt_template": str(legacy.get("review_system_prompt_template") or ""), "enable_paper_attributes": True, "outline_mode": "lite", "post_refine_mode": "lite"},
        )

        if not caps_exists:
            self._save_config_list(self.system_capabilities_path, capabilities)

        # personal preferences
        if not prefs_exists:
            prefs = {
                "preferences": {
                    "citation_format": str(legacy.get("citation_format") or "apa"),
                    "plan_confirm": bool(legacy.get("plan_confirm", False)),
                },
                "created_at": now,
                "updated_at": now,
            }
            _write_json_atomic(self.personal_preferences_path, prefs)

        self._ensure_capability_param_defaults()

    def _ensure_capability_param_defaults(self) -> None:
        """Backfill new capability params on existing v2 installs."""
        from app.storage.runtime_settings import (
            ORCHESTRATOR_PARAM_DEFAULTS,
            PROMPTS_PARAM_DEFAULTS,
            WEB_FETCH_PARAM_DEFAULTS,
            WEB_SEARCH_PARAM_DEFAULTS,
        )

        if not self.system_capabilities_path.is_file():
            return
        caps = self._load_config_list(self.system_capabilities_path)
        defaults_by_cap = {
            "web_search": WEB_SEARCH_PARAM_DEFAULTS,
            "web_fetch": WEB_FETCH_PARAM_DEFAULTS,
            "orchestrator": ORCHESTRATOR_PARAM_DEFAULTS,
            "prompts": PROMPTS_PARAM_DEFAULTS,
        }
        changed = False
        for cap in caps:
            cap_id = str(cap.get("capability_id") or "")
            defaults = defaults_by_cap.get(cap_id)
            if not defaults:
                continue
            params = cap.get("params") if isinstance(cap.get("params"), dict) else {}
            merged = dict(params)
            cap_changed = False
            for key, val in defaults.items():
                if key not in merged:
                    merged[key] = val
                    cap_changed = True
            if cap_id == "web_fetch" and "max_source_chars" not in merged:
                merged["max_source_chars"] = 14_000
                cap_changed = True
            if cap_changed:
                cap["params"] = merged
                changed = True
        if changed:
            self._save_config_list(self.system_capabilities_path, caps)

    def list_system_credentials(self) -> list[dict[str, Any]]:
        self.ensure_settings_v2_migrated()
        return self._load_config_list(self.system_credentials_path)

    def save_system_credentials(self, items: list[dict[str, Any]]) -> None:
        self.ensure_settings_v2_migrated()
        self._save_config_list(self.system_credentials_path, items)

    def list_system_instances(self) -> list[dict[str, Any]]:
        self.ensure_settings_v2_migrated()
        return self._load_config_list(self.system_instances_path)

    def save_system_instances(self, items: list[dict[str, Any]]) -> None:
        self.ensure_settings_v2_migrated()
        self._save_config_list(self.system_instances_path, items)

    def list_system_capabilities(self) -> list[dict[str, Any]]:
        self.ensure_settings_v2_migrated()
        return self._load_config_list(self.system_capabilities_path)

    def save_system_capabilities(self, items: list[dict[str, Any]]) -> None:
        self.ensure_settings_v2_migrated()
        self._save_config_list(self.system_capabilities_path, items)

    def get_personal_preferences(self) -> dict[str, Any]:
        self.ensure_settings_v2_migrated()
        data = self._load_config_obj(self.personal_preferences_path, {"preferences": {}})
        prefs = data.get("preferences") or {}
        if not isinstance(prefs, dict):
            prefs = {}
        return {
            "citation_format": str(prefs.get("citation_format") or "apa").strip().lower(),
            "plan_confirm": bool(prefs.get("plan_confirm", False)),
        }

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
        _write_json_atomic(self.personal_preferences_path, out)
        return self.get_personal_preferences()

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
        title_auto_set: bool | None = None,
    ) -> Optional[dict[str, Any]]:
        meta = self.get_session(session_id)
        if not meta:
            return None
        now = _utc_now()
        if title is not None:
            meta["title"] = title
        if pinned is not None:
            meta["pinned"] = pinned
        if title_auto_set is not None:
            meta["title_auto_set"] = title_auto_set
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

    def patch_session_meta(
        self,
        session_id: str,
        patch: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        meta = self.get_session(session_id)
        if not meta:
            return None
        now = _utc_now()
        for key, value in patch.items():
            if value is not None:
                meta[key] = value
        meta["updated_at"] = now
        _write_json_atomic(self.root / "sessions" / session_id / "meta.json", meta)
        return meta

    def save_corpus(self, session_id: str, data: dict[str, Any]) -> None:
        data = dict(data)
        data["updated_at"] = _utc_now()
        path = self.root / "sessions" / session_id / "corpus.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(path, data)

    def load_corpus(self, session_id: str) -> dict[str, Any] | None:
        path = self.root / "sessions" / session_id / "corpus.json"
        if not path.is_file():
            return None
        data = _read_json(path, None)
        return data if isinstance(data, dict) else None

    def save_outline(self, session_id: str, data: dict[str, Any]) -> None:
        payload = dict(data)
        payload["updated_at"] = _utc_now()
        path = self.root / "sessions" / session_id / "outline.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(path, payload)

    def load_outline(self, session_id: str) -> dict[str, Any] | None:
        path = self.root / "sessions" / session_id / "outline.json"
        if not path.is_file():
            return None
        data = _read_json(path, None)
        return data if isinstance(data, dict) else None

    def has_corpus(self, session_id: str) -> bool:
        return self.load_corpus(session_id) is not None

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

    def load_first_user_message(self, session_id: str, *, max_chars: int = 800) -> str:
        """First user turn in session (for library provenance preview)."""
        msg_path = self.root / "sessions" / session_id / "messages.jsonl"
        if not msg_path.is_file():
            return ""
        try:
            with open(msg_path, encoding="utf-8") as f:
                for ln in f:
                    line = ln.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
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
        except OSError:
            return ""
        return ""

    def save_review_artifact(
        self,
        session_id: str,
        content: str,
    ) -> tuple[Path, str]:
        return self._save_markdown_artifact(
            session_id,
            content,
            kind="review",
            meta_key="review_versions",
        )

    def save_matrix_artifact(
        self,
        session_id: str,
        content: str,
    ) -> tuple[Path, str]:
        return self._save_markdown_artifact(
            session_id,
            content,
            kind="matrix",
            meta_key="matrix_versions",
        )

    def _save_markdown_artifact(
        self,
        session_id: str,
        content: str,
        *,
        kind: str,
        meta_key: str,
    ) -> tuple[Path, str]:
        art_dir = self.root / "artifacts" / session_id
        art_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        version_id = f"{kind}_{uuid.uuid4().hex[:12]}"
        filename = f"{kind}-{ts}.md"
        path = art_dir / filename
        path.write_text(content, encoding="utf-8")
        latest = art_dir / f"{kind}-latest.md"
        latest.write_text(content, encoding="utf-8")
        meta = self.get_session(session_id)
        if meta is not None:
            versions = list(meta.get(meta_key) or [])
            versions.append(
                {
                    "id": version_id,
                    "filename": filename,
                    "created_at": _utc_now(),
                }
            )
            meta[meta_key] = versions[-20:]
            meta["updated_at"] = _utc_now()
            _write_json_atomic(
                self.root / "sessions" / session_id / "meta.json",
                meta,
            )
        return path, version_id

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

    def get_latest_matrix(self, session_id: str) -> dict[str, Any] | None:
        art_dir = self.root / "artifacts" / session_id
        latest = art_dir / "matrix-latest.md"
        if latest.is_file():
            return {
                "filename": "matrix-latest.md",
                "content": latest.read_text(encoding="utf-8"),
                "updated_at": datetime.fromtimestamp(
                    latest.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
            }
        if not art_dir.is_dir():
            return None
        files = sorted(art_dir.glob("matrix-*.md"), key=lambda p: p.stat().st_mtime)
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
