from __future__ import annotations

import uuid
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agents.agent_settings import MAX_FETCH_URLS_CAP, TAVILY_MAX_RESULTS_CAP
from app.agents.literature_source import normalize_literature_source_mode
from app.agents.review_prompt import (
    MAX_REVIEW_SYSTEM_PROMPT_LEN,
    default_review_system_prompt_template,
)
from app.agents.tavily_key import tavily_key_hint
from app.agents.tools.tavily_search import tavily_search
from app.core.response import err, ok
from app.storage.file_store import get_store

router = APIRouter(prefix="/settings", tags=["settings"])


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
    safe["has_tavily"] = bool(merged.get("tavily_api_key"))
    safe["has_jina"] = bool(merged.get("jina_api_key"))
    provider = merged.get("llm_provider") or "openai"
    safe["has_llm"] = bool(merged.get("llm_api_key")) or provider == "ollama"
    safe["llm_group_id"] = merged.get("llm_group_id") or ""
    for k in ("tavily_api_key", "jina_api_key", "llm_api_key"):
        if safe.get(k):
            safe[k] = _mask_secret(str(merged.get(k) or ""))
    safe["review_system_prompt_default"] = default_review_system_prompt_template()
    safe["review_system_prompt_template"] = str(
        merged.get("review_system_prompt_template") or ""
    )
    return safe


# -------------------- legacy agent settings (for current frontend) --------------------
class AgentSettingsBody(BaseModel):
    tavily_api_key: str | None = None
    jina_api_key: str | None = None
    llm_provider: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_base_url: str | None = None
    llm_group_id: str | None = None
    fetch_parallel: int | None = None
    fetch_timeout_sec: float | None = None
    tavily_max_results: int | None = None
    max_fetch_urls: int | None = None
    literature_source_mode: str | None = None
    tavily_retry_count: int | None = None
    fetch_retry_count: int | None = None
    fetch_retry_delay_ms: int | None = None
    plan_confirm: bool | None = None
    citation_format: str | None = None
    use_llm_planner: bool | None = None
    orchestrator_mode: str | None = None
    orchestrator_use_reasoning: bool | None = None
    orchestrator_model: str | None = None
    orchestrator_max_tokens_per_phase: int | None = None
    review_system_prompt_template: str | None = None


@router.get("/agent")
async def get_agent_settings():
    merged = get_store().get_agent_settings_merged()
    return ok(_agent_settings_response(merged))


@router.post("/agent")
async def save_agent_settings(body: AgentSettingsBody):
    partial = body.model_dump(exclude_none=True)

    if "citation_format" in partial:
        raw = str(partial["citation_format"]).strip().lower()
        if raw not in ("apa", "acm"):
            return err("citation_format 须为 apa 或 acm")
        partial["citation_format"] = raw

    if "tavily_max_results" in partial:
        partial["tavily_max_results"] = max(
            1, min(int(partial["tavily_max_results"]), TAVILY_MAX_RESULTS_CAP)
        )
    if "max_fetch_urls" in partial:
        partial["max_fetch_urls"] = max(
            1, min(int(partial["max_fetch_urls"]), MAX_FETCH_URLS_CAP)
        )
    if "literature_source_mode" in partial:
        partial["literature_source_mode"] = normalize_literature_source_mode(
            partial["literature_source_mode"]
        )
    if "tavily_retry_count" in partial:
        partial["tavily_retry_count"] = max(0, min(int(partial["tavily_retry_count"]), 3))
    if "fetch_retry_count" in partial:
        partial["fetch_retry_count"] = max(0, min(int(partial["fetch_retry_count"]), 3))
    if "fetch_retry_delay_ms" in partial:
        partial["fetch_retry_delay_ms"] = max(
            0, min(int(partial["fetch_retry_delay_ms"]), 5000)
        )

    if "tavily_api_key" in partial:
        hint = tavily_key_hint(partial["tavily_api_key"])
        if hint:
            return err(hint)

    if "orchestrator_mode" in partial:
        mode = str(partial["orchestrator_mode"]).strip().lower()
        if mode not in ("off", "lite", "full"):
            return err("orchestrator_mode 须为 off、lite 或 full")
        partial["orchestrator_mode"] = mode

    if "orchestrator_max_tokens_per_phase" in partial:
        partial["orchestrator_max_tokens_per_phase"] = max(
            80, min(int(partial["orchestrator_max_tokens_per_phase"]), 500)
        )

    if "review_system_prompt_template" in partial:
        tpl = str(partial["review_system_prompt_template"])
        if len(tpl) > MAX_REVIEW_SYSTEM_PROMPT_LEN:
            return err(f"综述生成 system prompt 过长（最多 {MAX_REVIEW_SYSTEM_PROMPT_LEN} 字符）")
        partial["review_system_prompt_template"] = tpl

    saved = get_store().save_agent_settings(partial)
    return ok(_agent_settings_response(saved), message="设置已保存")


class TestTavilyBody(BaseModel):
    api_key: str | None = None
    query: str = "transformer attention paper arxiv"


@router.post("/agent/test-tavily")
async def test_tavily(body: TestTavilyBody):
    merged = get_store().get_agent_settings_merged()
    key = body.api_key or merged.get("tavily_api_key")
    if not key:
        return err("未配置 Tavily API Key")
    hint = tavily_key_hint(key)
    if hint:
        return err(hint)
    try:
        data = await tavily_search(key, body.query, max_results=3)
        hits = len(data.get("results") or [])
        return ok({"hits": hits, "answer_preview": str(data.get("answer") or "")[:200]})
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            return err("Tavily 返回 401 Unauthorized：Key 无效、已撤销或已过期。")
        return err(f"Tavily 请求失败: {e}")
    except httpx.HTTPError as e:
        return err(f"Tavily 请求失败: {e}")


# -------------------- personal --------------------
class PersonalPreferencesBody(BaseModel):
    citation_format: str | None = None
    plan_confirm: bool | None = None


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
        ref = (c.get("primary_ref") or {}) if isinstance(c, dict) else {}
        kind = str(ref.get("kind") or "")
        rid = str(ref.get("id") or "")
        ok_ = True
        if kind == "credential":
            ok_ = bool(cred_ok.get(rid))
        elif kind == "instance":
            ok_ = bool(inst_ok.get(rid))
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
        }
    )


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
        hint = tavily_key_hint(secret)
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
            hint = tavily_key_hint(sec)
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
            return err("未配置 Tavily API Key", _credential_test_payload(c))
        hint = tavily_key_hint(secret)
        if hint:
            c["status"] = "fail"
            c["last_verified_at"] = now
            _persist()
            return err(hint, _credential_test_payload(c))
        try:
            data = await tavily_search(secret, body.query, max_results=3)
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
                return err(
                    "Tavily 返回 401 Unauthorized：Key 无效、已撤销或已过期。",
                    _credential_test_payload(c),
                )
            return err(f"Tavily 请求失败: {e}", _credential_test_payload(c))
        except httpx.HTTPError as e:
            c["status"] = "fail"
            c["last_verified_at"] = now
            _persist()
            return err(f"Tavily 请求失败: {e}", _credential_test_payload(c))

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
    for k, v in partial.items():
        cap[k] = v
    from datetime import datetime, timezone as _tz

    cap["updated_at"] = datetime.now(_tz.utc).isoformat()
    store.save_system_capabilities(items)
    return ok(_public_capability(cap), message="能力配置已保存")


@router.post("/system/capabilities/{capability_id}/test")
async def test_capability(capability_id: str):
    return ok({"ok": True, "note": "capability test 暂未实现"})
