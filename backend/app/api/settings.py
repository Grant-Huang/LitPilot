from __future__ import annotations

import uuid
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agents.agent_settings import MAX_FETCH_URLS_CAP, SEARCH_MAX_RESULTS_CAP
from app.agents.prompt_registry import (
    all_prompt_defaults,
    clamp_prompt_params,
    prompt_registry_metadata,
)
from app.agents.search_credential_hint import search_credential_secret_hint
from app.agents.tools.providers.tavily import search as tavily_provider_search
from app.agents.tools.web_providers import SEARCH_PROVIDER_LABELS
from app.core.response import err, ok
from app.storage.file_store import get_store

router = APIRouter(prefix="/settings", tags=["settings"])


def _capability_params(cap: dict) -> dict:
    params = dict(cap.get("params") or {}) if isinstance(cap.get("params"), dict) else {}
    override = cap.get("override_params")
    if isinstance(override, dict) and override:
        params.update(override)
    return params


def _capability_health_ok(cap: dict, *, cred_ok: dict, inst_ok: dict) -> bool:
    cap_id = str(cap.get("capability_id") or "")
    params = _capability_params(cap)
    if cap_id == "web_search":
        sp = str(params.get("search_provider") or "multi_academic").strip().lower()
        if sp in ("native", "openalex"):
            return True
    if cap_id == "web_fetch":
        fp = str(params.get("fetch_provider") or "native").strip().lower()
        if fp == "native":
            return True
    ref = (cap.get("primary_ref") or {}) if isinstance(cap.get("primary_ref"), dict) else {}
    kind = str(ref.get("kind") or "")
    rid = str(ref.get("id") or "")
    if kind == "credential":
        return bool(cred_ok.get(rid))
    if kind == "instance":
        return bool(inst_ok.get(rid))
    return cap_id not in ("web_search", "web_fetch", "review_main", "orchestrator")


def _mask_secret(secret: str) -> str:
    s = str(secret or "")
    if not s:
        return ""
    return "***" + s[-4:]


def _find_by_id(items: list[dict], id_: str) -> dict | None:
    for it in items:
        if str(it.get("id")) == str(id_):
            return it
    return None


def _public_credential(c: dict) -> dict:
    out = dict(c)
    secret = str(out.pop("secret", "") or "")
    out["has_secret"] = bool(secret)
    out["masked_secret"] = _mask_secret(secret)
    return out


def _public_instance(i: dict) -> dict:
    return dict(i)


def _public_capability(c: dict) -> dict:
    return dict(c)


def _agent_settings_response(merged: dict) -> dict:
    safe = dict(merged)
    safe["has_web_search"] = bool(merged.get("web_search_api_key"))
    safe["has_fetch"] = bool(merged.get("fetch_api_key"))
    provider = merged.get("llm_provider") or "openai"
    safe["has_llm"] = bool(merged.get("llm_api_key")) or provider == "ollama"
    safe["llm_group_id"] = merged.get("llm_group_id") or ""
    for k in ("web_search_api_key", "fetch_api_key", "llm_api_key"):
        if safe.get(k):
            safe[k] = _mask_secret(str(merged.get(k) or ""))
    return safe


# -------------------- legacy agent settings (for current frontend) --------------------
class AgentSettingsBody(BaseModel):
    web_search_api_key: str | None = None
    fetch_api_key: str | None = None
    llm_provider: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_base_url: str | None = None
    llm_group_id: str | None = None
    fetch_parallel: int | None = None
    fetch_timeout_sec: float | None = None
    search_max_results: int | None = None
    max_fetch_urls: int | None = None
    search_retry_count: int | None = None
    fetch_retry_count: int | None = None
    fetch_retry_delay_ms: int | None = None
    citation_format: str | None = None
    use_llm_planner: bool | None = None
    orchestrator_mode: str | None = None
    orchestrator_use_reasoning: bool | None = None
    orchestrator_model: str | None = None
    orchestrator_max_tokens_per_phase: int | None = None


@router.get("/agent")
async def get_agent_settings():
    merged = get_store().get_agent_settings_merged()
    return ok(_agent_settings_response(merged))


@router.post("/agent")
async def save_agent_settings(body: AgentSettingsBody):
    from app.agents.agent_settings import _clear_all_caches

    partial = body.model_dump(exclude_none=True)

    if "citation_format" in partial:
        raw = str(partial["citation_format"]).strip().lower()
        if raw not in ("apa", "acm"):
            return err("citation_format 须为 apa 或 acm")
        partial["citation_format"] = raw

    if "search_max_results" in partial:
        partial["search_max_results"] = max(
            1, min(int(partial["search_max_results"]), SEARCH_MAX_RESULTS_CAP)
        )
    if "max_fetch_urls" in partial:
        partial["max_fetch_urls"] = max(
            1, min(int(partial["max_fetch_urls"]), MAX_FETCH_URLS_CAP)
        )
    if "search_retry_count" in partial:
        partial["search_retry_count"] = max(0, min(int(partial["search_retry_count"]), 3))
    if "fetch_retry_count" in partial:
        partial["fetch_retry_count"] = max(0, min(int(partial["fetch_retry_count"]), 3))
    if "fetch_retry_delay_ms" in partial:
        partial["fetch_retry_delay_ms"] = max(
            0, min(int(partial["fetch_retry_delay_ms"]), 5000)
        )

    if "web_search_api_key" in partial:
        hint = search_credential_secret_hint("tavily", partial["web_search_api_key"])
        if hint:
            return err(hint)

    if "orchestrator_mode" in partial:
        partial.pop("orchestrator_mode", None)

    if "orchestrator_max_tokens_per_phase" in partial:
        partial["orchestrator_max_tokens_per_phase"] = max(
            80, min(int(partial["orchestrator_max_tokens_per_phase"]), 500)
        )

    saved = get_store().save_agent_settings(partial)
    _clear_all_caches()
    return ok(_agent_settings_response(saved), message="设置已保存")


# -------------------- personal --------------------
class PersonalPreferencesBody(BaseModel):
    citation_format: str | None = None


@router.get("/personal/preferences")
async def get_personal_preferences():
    prefs = get_store().get_personal_preferences()
    return ok(prefs)


@router.put("/personal/preferences")
async def save_personal_preferences(body: PersonalPreferencesBody):
    partial = body.model_dump(exclude_none=True)
    if "citation_format" in partial:
        raw = str(partial["citation_format"]).strip().lower()
        if raw not in ("apa", "acm"):
            return err("citation_format 须为 apa 或 acm")
        partial["citation_format"] = raw
    saved = get_store().save_personal_preferences(partial)
    return ok(saved, message="个人偏好已保存")


# -------------------- system overview --------------------
@router.get("/system/overview")
async def get_system_overview():
    store = get_store()
    creds = store.list_system_credentials()
    instances = store.list_system_instances()
    caps = store.list_system_capabilities()
    # derived health
    cred_ok = {
        c.get("id"): bool(c.get("secret"))
        for c in creds
        if isinstance(c, dict)
    }
    inst_ok = {
        i.get("id"): bool(i.get("credential_id")) and bool(cred_ok.get(i.get("credential_id")))
        for i in instances
        if isinstance(i, dict)
    }
    cap_health: list[dict] = []
    for c in caps:
        ok_ = _capability_health_ok(c, cred_ok=cred_ok, inst_ok=inst_ok)
        cap_health.append(
            {
                "capability_id": c.get("capability_id"),
                "label": c.get("label"),
                "enabled": bool(c.get("enabled", True)),
                "ok": bool(ok_),
                "primary_ref": c.get("primary_ref"),
            }
        )
    return ok(
        {
            "credentials": [_public_credential(c) for c in creds],
            "instances": [_public_instance(i) for i in instances],
            "capabilities": cap_health,
            "storage": store.get_storage_settings_public(),
        }
    )


class StorageSettingsUpdateBody(BaseModel):
    database_url: str | None = None
    auth_token: str | None = None


@router.get("/system/storage")
async def get_system_storage():
    store = get_store()
    return ok(store.get_storage_settings_public())


@router.put("/system/storage")
async def update_system_storage(body: StorageSettingsUpdateBody):
    store = get_store()
    partial = body.model_dump(exclude_none=True)
    if not partial:
        return err("无有效更新字段")
    if "database_url" in partial:
        url = str(partial["database_url"] or "").strip()
        if url and not url.startswith(("libsql://", "https://", "http://")):
            return err("database_url 须以 libsql:// 或 https:// 开头")
        partial["database_url"] = url
    saved = store.save_storage_settings(partial)
    return ok(saved, message="存储配置已保存")


# -------------------- system credentials --------------------
class CredentialCreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: str = Field(min_length=1, max_length=60)
    secret: str | None = None
    base_url: str | None = None
    group_id: str | None = None


class CredentialUpdateBody(BaseModel):
    name: str | None = None
    secret: str | None = None  # empty string means clear
    base_url: str | None = None
    group_id: str | None = None
    status: str | None = None
    last_verified_at: str | None = None


@router.get("/system/credentials")
async def list_credentials(type: str | None = None):
    items = get_store().list_system_credentials()
    if type:
        items = [c for c in items if str(c.get("type") or "") == str(type)]
    return ok({"items": [_public_credential(c) for c in items]})


@router.post("/system/credentials")
async def create_credential(body: CredentialCreateBody):
    store = get_store()
    items = store.list_system_credentials()
    cid = uuid.uuid4().hex
    secret = str(body.secret or "")
    if body.type == "tavily" and secret:
        hint = search_credential_secret_hint("tavily", secret)
        if hint:
            return err(hint)
    # minimal timestamp without importing private helpers
    from datetime import datetime, timezone as _tz

    ts = datetime.now(_tz.utc).isoformat()
    items.append(
        {
            "id": cid,
            "type": body.type,
            "name": body.name,
            "secret": secret,
            "base_url": body.base_url or "",
            "group_id": body.group_id or "",
            "status": "unknown",
            "last_verified_at": None,
            "created_at": ts,
            "updated_at": ts,
        }
    )
    store.save_system_credentials(items)
    created = _find_by_id(items, cid) or {}
    return ok(_public_credential(created), message="凭据已创建")


@router.get("/system/credentials/{credential_id}")
async def get_credential(credential_id: str):
    items = get_store().list_system_credentials()
    c = _find_by_id(items, credential_id)
    if not c:
        raise HTTPException(status_code=404, detail="credential not found")
    return ok(_public_credential(c))


@router.put("/system/credentials/{credential_id}")
async def update_credential(credential_id: str, body: CredentialUpdateBody):
    store = get_store()
    items = store.list_system_credentials()
    c = _find_by_id(items, credential_id)
    if not c:
        raise HTTPException(status_code=404, detail="credential not found")
    partial = body.model_dump(exclude_none=True)
    if "secret" in partial:
        sec = str(partial["secret"] or "")
        if c.get("type") == "tavily" and sec:
            hint = search_credential_secret_hint("tavily", sec)
            if hint:
                return err(hint)
        c["secret"] = sec
        c["status"] = "unknown"
        c["last_verified_at"] = None
        partial.pop("secret", None)
    for k, v in partial.items():
        c[k] = v
    from datetime import datetime, timezone as _tz

    c["updated_at"] = datetime.now(_tz.utc).isoformat()
    store.save_system_credentials(items)
    return ok(_public_credential(c), message="凭据已保存")


@router.delete("/system/credentials/{credential_id}")
async def delete_credential(credential_id: str):
    store = get_store()
    creds = store.list_system_credentials()
    instances = store.list_system_instances()
    used_by = [
        i.get("id")
        for i in instances
        if str(i.get("credential_id") or "") == str(credential_id)
    ]
    if used_by:
        return err("凭据正在被实例引用，无法删除", data={"used_by_instances": used_by})
    new_items = [c for c in creds if str(c.get("id")) != str(credential_id)]
    store.save_system_credentials(new_items)
    return ok({"deleted": True})


class CredentialTestBody(BaseModel):
    query: str = "transformer attention paper arxiv"


def _credential_test_payload(c: dict, **extra) -> dict:
    return {"credential": _public_credential(c), **extra}


@router.post("/system/credentials/{credential_id}/test")
async def test_credential(credential_id: str, body: CredentialTestBody):
    store = get_store()
    creds = store.list_system_credentials()
    c = _find_by_id(creds, credential_id)
    if not c:
        raise HTTPException(status_code=404, detail="credential not found")
    ctype = str(c.get("type") or "")
    secret = str(c.get("secret") or "")
    from datetime import datetime, timezone as _tz

    now = datetime.now(_tz.utc).isoformat()

    def _persist() -> None:
        store.save_system_credentials(creds)

    if ctype == "tavily":
        if not secret:
            c["status"] = "fail"
            c["last_verified_at"] = now
            _persist()
            return err("未配置 web_search API Key", _credential_test_payload(c))
        hint = search_credential_secret_hint("tavily", secret)
        if hint:
            c["status"] = "fail"
            c["last_verified_at"] = now
            _persist()
            return err(hint, _credential_test_payload(c))
        try:
            data = await tavily_provider_search(secret, body.query, max_results=3)
            hits = len(data.get("results") or [])
            c["status"] = "ok"
            c["last_verified_at"] = now
            _persist()
            return ok(_credential_test_payload(c, ok=True, hits=hits))
        except httpx.HTTPStatusError as e:
            c["status"] = "fail"
            c["last_verified_at"] = now
            _persist()
            if e.response.status_code == 401:
                label = SEARCH_PROVIDER_LABELS.get("tavily", "tavily")
                return err(
                    f"{label} 返回 401 Unauthorized：Key 无效、已撤销或已过期。",
                    _credential_test_payload(c),
                )
            label = SEARCH_PROVIDER_LABELS.get("tavily", "tavily")
            return err(f"{label} 请求失败: {e}", _credential_test_payload(c))
        except httpx.HTTPError as e:
            c["status"] = "fail"
            c["last_verified_at"] = now
            _persist()
            label = SEARCH_PROVIDER_LABELS.get("tavily", "tavily")
            return err(f"{label} 请求失败: {e}", _credential_test_payload(c))

    if ctype == "semantic_scholar":
        if not secret:
            c["status"] = "fail"
            c["last_verified_at"] = now
            _persist()
            return err("未配置 Semantic Scholar API Key", _credential_test_payload(c))
        try:
            from app.agents.tools.providers.academic import semantic_scholar as ss_provider

            rows = await ss_provider.search(
                body.query or "transformer attention",
                limit=3,
                min_year=2017,
                api_key=secret,
            )
            hits = len(rows)
            c["status"] = "ok"
            c["last_verified_at"] = now
            _persist()
            return ok(_credential_test_payload(c, ok=True, hits=hits))
        except httpx.HTTPStatusError as e:
            c["status"] = "fail"
            c["last_verified_at"] = now
            _persist()
            if e.response.status_code == 429:
                return err(
                    "Semantic Scholar 429：请稍后重试或检查 Key 配额。",
                    _credential_test_payload(c),
                )
            return err(f"Semantic Scholar 请求失败: {e}", _credential_test_payload(c))
        except httpx.HTTPError as e:
            c["status"] = "fail"
            c["last_verified_at"] = now
            _persist()
            return err(f"Semantic Scholar 请求失败: {e}", _credential_test_payload(c))

    if ctype == "brave":
        if not secret:
            c["status"] = "fail"
            c["last_verified_at"] = now
            _persist()
            return err("未配置 Brave Search API Key", _credential_test_payload(c))
        try:
            from app.agents.tools.providers.brave import search as brave_provider_search

            data = await brave_provider_search(secret, body.query, max_results=3)
            hits = len(data.get("results") or [])
            c["status"] = "ok"
            c["last_verified_at"] = now
            _persist()
            return ok(_credential_test_payload(c, ok=True, hits=hits))
        except httpx.HTTPStatusError as e:
            c["status"] = "fail"
            c["last_verified_at"] = now
            _persist()
            if e.response.status_code in (401, 403):
                return err(
                    "Brave 返回 401/403：Key 无效或未授权。",
                    _credential_test_payload(c),
                )
            return err(f"Brave 请求失败: {e}", _credential_test_payload(c))
        except httpx.HTTPError as e:
            c["status"] = "fail"
            c["last_verified_at"] = now
            _persist()
            return err(f"Brave 请求失败: {e}", _credential_test_payload(c))

    # Best-effort: for other credential types, treat non-empty secret as "ok".
    if secret:
        c["status"] = "ok"
        c["last_verified_at"] = now
        _persist()
        return ok(_credential_test_payload(c, ok=True, note=f"{ctype} 已记录为通过（基础检查）"))
    c["status"] = "fail"
    c["last_verified_at"] = now
    _persist()
    return err(f"{ctype} 未配置 secret，测试未通过", _credential_test_payload(c))


# -------------------- system instances --------------------
class InstanceCreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    provider: str = Field(min_length=1, max_length=60)
    credential_id: str = Field(min_length=1, max_length=80)
    model_name: str = Field(min_length=1, max_length=80)
    default_params: dict | None = None


class InstanceUpdateBody(BaseModel):
    name: str | None = None
    credential_id: str | None = None
    model_name: str | None = None
    default_params: dict | None = None
    status: str | None = None
    last_verified_at: str | None = None


@router.get("/system/instances")
async def list_instances(provider: str | None = None):
    items = get_store().list_system_instances()
    if provider:
        items = [i for i in items if str(i.get("provider") or "") == str(provider)]
    return ok({"items": [_public_instance(i) for i in items]})


@router.post("/system/instances")
async def create_instance(body: InstanceCreateBody):
    store = get_store()
    items = store.list_system_instances()
    iid = uuid.uuid4().hex
    from datetime import datetime, timezone as _tz

    ts = datetime.now(_tz.utc).isoformat()
    items.append(
        {
            "id": iid,
            "name": body.name,
            "provider": body.provider,
            "credential_id": body.credential_id,
            "model_name": body.model_name,
            "default_params": body.default_params or {},
            "status": "unknown",
            "last_verified_at": None,
            "created_at": ts,
            "updated_at": ts,
        }
    )
    store.save_system_instances(items)
    created = _find_by_id(items, iid) or {}
    return ok(_public_instance(created), message="实例已创建")


@router.get("/system/instances/{instance_id}")
async def get_instance(instance_id: str):
    store = get_store()
    items = store.list_system_instances()
    inst = _find_by_id(items, instance_id)
    if not inst:
        raise HTTPException(status_code=404, detail="instance not found")
    caps = store.list_system_capabilities()
    used_by = []
    for c in caps:
        ref = c.get("primary_ref") or {}
        if str(ref.get("kind") or "") == "instance" and str(ref.get("id") or "") == str(
            instance_id
        ):
            used_by.append({"capability_id": c.get("capability_id"), "label": c.get("label")})
    return ok({"instance": _public_instance(inst), "used_by": used_by})


@router.put("/system/instances/{instance_id}")
async def update_instance(instance_id: str, body: InstanceUpdateBody):
    store = get_store()
    items = store.list_system_instances()
    inst = _find_by_id(items, instance_id)
    if not inst:
        raise HTTPException(status_code=404, detail="instance not found")
    partial = body.model_dump(exclude_none=True)
    for k, v in partial.items():
        inst[k] = v
    from datetime import datetime, timezone as _tz

    inst["updated_at"] = datetime.now(_tz.utc).isoformat()
    store.save_system_instances(items)
    return ok(_public_instance(inst), message="实例已保存")


@router.delete("/system/instances/{instance_id}")
async def delete_instance(instance_id: str):
    store = get_store()
    caps = store.list_system_capabilities()
    used_by = []
    for c in caps:
        ref = c.get("primary_ref") or {}
        if str(ref.get("kind") or "") == "instance" and str(ref.get("id") or "") == str(
            instance_id
        ):
            used_by.append(c.get("capability_id"))
    if used_by:
        return err("实例正在被能力引用，无法删除", data={"used_by_capabilities": used_by})
    items = store.list_system_instances()
    store.save_system_instances([i for i in items if str(i.get("id")) != str(instance_id)])
    return ok({"deleted": True})


@router.post("/system/instances/{instance_id}/test")
async def test_instance(instance_id: str):
    store = get_store()
    items = store.list_system_instances()
    inst = _find_by_id(items, instance_id)
    if not inst:
        raise HTTPException(status_code=404, detail="instance not found")
    creds = store.list_system_credentials()
    cred = _find_by_id(creds, str(inst.get("credential_id") or ""))
    from datetime import datetime, timezone as _tz

    now = datetime.now(_tz.utc).isoformat()
    if not cred:
        inst["status"] = "fail"
        inst["last_verified_at"] = now
        store.save_system_instances(items)
        return err("实例绑定的 credential 不存在", {"instance": _public_instance(inst)})
    secret = str(cred.get("secret") or "")
    if not secret and not str(cred.get("type") or "").startswith("llm:ollama"):
        inst["status"] = "fail"
        inst["last_verified_at"] = now
        store.save_system_instances(items)
        return err("实例绑定的 credential 未配置 secret", {"instance": _public_instance(inst)})
    inst["status"] = "ok"
    inst["last_verified_at"] = now
    store.save_system_instances(items)
    return ok({"ok": True, "note": "已通过基础检查", "instance": _public_instance(inst)})


# -------------------- system capabilities (bindings) --------------------
@router.get("/system/capabilities")
async def list_capabilities():
    items = get_store().list_system_capabilities()
    return ok({"items": [_public_capability(c) for c in items]})


@router.get("/system/prompts/defaults")
async def get_prompt_template_defaults():
    return ok(
        {
            "defaults": all_prompt_defaults(),
            "meta": prompt_registry_metadata(),
        }
    )


class CapabilityUpdateBody(BaseModel):
    enabled: bool | None = None
    primary_ref: dict | None = None
    override_params: dict | None = None
    params: dict | None = None


@router.put("/system/capabilities/{capability_id}")
async def update_capability(capability_id: str, body: CapabilityUpdateBody):
    store = get_store()
    items = store.list_system_capabilities()
    cap = None
    for c in items:
        if str(c.get("capability_id") or "") == str(capability_id):
            cap = c
            break
    if not cap:
        raise HTTPException(status_code=404, detail="capability not found")
    partial = body.model_dump(exclude_none=True)
    if str(capability_id) == "prompts" and isinstance(partial.get("params"), dict):
        partial["params"] = clamp_prompt_params(partial["params"])
    for k, v in partial.items():
        cap[k] = v
    from datetime import datetime, timezone as _tz

    cap["updated_at"] = datetime.now(_tz.utc).isoformat()
    store.save_system_capabilities(items)
    return ok(_public_capability(cap), message="能力配置已保存")


class WebFetchTestBody(BaseModel):
    url: str
    provider: str | None = None
    pdf_extract_backend: str | None = None


class CapabilityTestBody(BaseModel):
    url: str | None = None
    query: str | None = None
    provider: str | None = None
    pdf_extract_backend: str | None = None


async def _web_fetch_test_payload(body: WebFetchTestBody) -> dict[str, Any]:
    from app.agents.agent_settings import (
        get_fetch_timeout_sec,
        get_fetch_api_key,
        get_pdf_extract_backend,
        get_web_fetch_provider,
    )
    from app.agents.content_pipeline import (
        clean_html_to_text,
        extract_main_content,
        strip_instruction_injections,
    )
    from app.agents.tools.pdf_text import PYMUPDF4LLM_LICENSE_NOTE, pymupdf4llm_available
    from app.agents.tools.web_providers import normalize_fetch_provider, web_fetch_url_with_meta

    url = (body.url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError("请提供 http(s) URL")

    provider = normalize_fetch_provider(body.provider)
    if not body.provider:
        provider = await get_web_fetch_provider()

    timeout = await get_fetch_timeout_sec()
    fetch_api_key = await get_fetch_api_key() or None
    pdf_backend = body.pdf_extract_backend
    if not pdf_backend:
        pdf_backend = await get_pdf_extract_backend()
    fetched = await web_fetch_url_with_meta(
        url,
        provider=provider,
        api_key=fetch_api_key,
        timeout=timeout,
        pdf_extract_backend=pdf_backend,
    )
    raw = str(fetched.get("text") or "")

    is_pdf = bool(fetched.get("is_pdf"))
    resolved_pdf_url = fetched.get("resolved_pdf_url")
    final_url = str(fetched.get("final_url") or url)
    used_pdf_backend = fetched.get("pdf_extract_backend")
    extra_note = ""
    if used_pdf_backend == "pymupdf4llm" and not pymupdf4llm_available():
        extra_note = "pymupdf4llm 未安装，已回退 pypdf；可选：pip install pymupdf4llm"
    if is_pdf and raw.strip():
        text = strip_instruction_injections(raw.strip())
    else:
        text = strip_instruction_injections(extract_main_content(clean_html_to_text(raw)))
    preview = text[:1200] if text else (raw[:1200] if raw else "")
    title = ""
    for ln in (raw or "").splitlines()[:40]:
        s = ln.strip()
        if s.startswith("# "):
            title = s[2:].strip()[:200]
            break
        if s.startswith("## ") and not title:
            title = s[3:].strip()[:200]

    return {
        "ok": bool(text and len(text) >= 80),
        "provider": provider,
        "url": url,
        "final_url": final_url,
        "resolved_pdf_url": resolved_pdf_url,
        "is_pdf": is_pdf,
        "pdf_extract_backend": used_pdf_backend,
        "pymupdf4llm_license_note": (
            PYMUPDF4LLM_LICENSE_NOTE if used_pdf_backend == "pymupdf4llm" else None
        ),
        "raw_bytes": len(raw or ""),
        "text_chars": len(text or ""),
        "title": title,
        "preview": preview,
        "note": extra_note or (
            "PDF 已解析但正文过短"
            if is_pdf and text and len(text) < 80
            else ("正文过短" if text and len(text) < 80 else "")
        ),
    }


@router.post("/system/capabilities/web_fetch/test")
@router.post("/system/capabilities/web_fetch/test-url")
async def test_web_fetch(body: WebFetchTestBody):
    """Probe URL fetch with current or overridden fetch_provider."""
    try:
        return ok(await _web_fetch_test_payload(body))
    except ValueError as e:
        return err(str(e))
    except Exception as e:
        from app.agents.tools.web_providers import normalize_fetch_provider

        provider = normalize_fetch_provider(body.provider)
        return err(
            f"抓取失败: {e}",
            data={"ok": False, "provider": provider, "url": (body.url or "").strip()},
        )


async def _web_search_test_payload(body: CapabilityTestBody) -> dict[str, Any]:
    from app.agents.agent_settings import get_web_search_api_key, get_web_search_provider
    from app.agents.tools.web_providers import normalize_search_provider, web_search_query

    query = (body.query or "machine learning survey").strip()
    provider = normalize_search_provider(body.provider)
    if not body.provider:
        provider = await get_web_search_provider()
    api_key = await get_web_search_api_key() or None
    if provider in ("tavily", "brave") and not api_key:
        raise ValueError(f"请先在凭据页配置 {provider} API Key")
    data = await web_search_query(
        query,
        provider=provider,
        api_key=api_key,
        max_results=3,
    )
    hits = data.get("results") if isinstance(data.get("results"), list) else []
    return {
        "ok": bool(hits),
        "provider": provider,
        "query": query,
        "hits": len(hits),
        "results": hits[:3],
        "note": f"命中 {len(hits)} 条" if hits else "无命中结果",
    }


@router.post("/system/capabilities/web_search/test")
async def test_web_search(body: CapabilityTestBody):
    """Probe search with current or overridden search_provider."""
    try:
        return ok(await _web_search_test_payload(body))
    except ValueError as e:
        return err(str(e))
    except Exception as e:
        from app.agents.tools.web_providers import normalize_search_provider

        provider = normalize_search_provider(body.provider)
        return err(
            f"检索失败: {e}",
            data={"ok": False, "provider": provider, "query": (body.query or "").strip()},
        )


@router.post("/system/capabilities/{capability_id}/test")
async def test_capability(capability_id: str, body: CapabilityTestBody | None = None):
    body = body or CapabilityTestBody()
    cap_id = str(capability_id or "").strip()

    if cap_id == "web_fetch":
        url = (body.url or "").strip()
        if not url:
            return err("请提供 url")
        try:
            payload = await _web_fetch_test_payload(
                WebFetchTestBody(
                    url=url,
                    provider=body.provider,
                    pdf_extract_backend=body.pdf_extract_backend,
                ),
            )
            return ok(payload)
        except ValueError as e:
            return err(str(e))
        except Exception as e:
            from app.agents.tools.web_providers import normalize_fetch_provider

            provider = normalize_fetch_provider(body.provider)
            return err(
                f"抓取失败: {e}",
                data={"ok": False, "provider": provider, "url": url},
            )

    if cap_id == "web_search":
        query = (body.query or "machine learning survey").strip()
        if not query:
            return err("请提供 query")
        try:
            return ok(await _web_search_test_payload(body))
        except ValueError as e:
            return err(str(e))
        except Exception as e:
            from app.agents.tools.web_providers import normalize_search_provider

            provider = normalize_search_provider(body.provider)
            return err(
                f"检索失败: {e}",
                data={"ok": False, "provider": provider, "query": query},
            )

    return err(f"不支持测试: {cap_id}")
