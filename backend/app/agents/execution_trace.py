"""构建可持久化的执行过程轨迹（与前端 executionTrace 对齐）。"""

from __future__ import annotations

import re
import uuid
from typing import Any


def new_trace() -> dict[str, Any]:
    return {"stages": [], "tools": [], "workflows": []}


def upsert_stage(trace: dict[str, Any], name: str, state: str) -> None:
    stages: list[dict[str, str]] = trace.setdefault("stages", [])
    stages[:] = [s for s in stages if s.get("name") != name]
    stages.append({"name": name, "state": state})


def append_tool(
    trace: dict[str, Any],
    *,
    tool_id: str,
    name: str,
    args: dict[str, Any],
    status: str,
    output: str = "",
    error: str | None = None,
    duration_ms: int | None = None,
) -> None:
    # 规范化 tool_id：开发阶段不考虑向前兼容，确保工具步骤在前端渲染时永不重复
    # 期望格式：tc_<12-hex>（与 _new_id("tc") 生成一致）
    tools: list[dict[str, Any]] = trace.setdefault("tools", [])
    existing_ids = {str(t.get("id") or "") for t in tools}
    want = str(tool_id or "").strip()
    ok = bool(re.fullmatch(r"tc_[0-9a-f]{12}", want))
    if (not ok) or (want in existing_ids):
        new_id = f"tc_{uuid.uuid4().hex[:12]}"
        if isinstance(args, dict):
            args.setdefault("_raw_tool_id", want)
        tool_id = new_id

    entry: dict[str, Any] = {
        "id": tool_id,
        "name": name,
        "args": args,
        "status": status,
    }
    if output:
        entry["output"] = output
    if error:
        entry["error"] = error
    if duration_ms is not None:
        entry["duration_ms"] = duration_ms
    tools.append(entry)


def record_literature_stats(trace: dict[str, Any], **kwargs: Any) -> None:
    stats = trace.setdefault("literatureStats", {})
    for key, value in kwargs.items():
        if value is not None:
            stats[key] = value


def append_workflow(
    trace: dict[str, Any],
    *,
    node_id: str,
    name: str,
    state: str,
    title: str = "",
    url: str = "",
    char_count: int | None = None,
    error: str | None = None,
    duration_ms: int | None = None,
) -> None:
    entry: dict[str, Any] = {
        "node_id": node_id,
        "name": name,
        "state": state,
    }
    if title:
        entry["title"] = title
    if url:
        entry["url"] = url
    if char_count is not None and char_count > 0:
        entry["char_count"] = char_count
    if error:
        entry["error"] = error
    if duration_ms is not None:
        entry["duration_ms"] = duration_ms
    trace.setdefault("workflows", []).append(entry)
