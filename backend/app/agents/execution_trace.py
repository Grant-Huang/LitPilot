"""构建可持久化的执行过程轨迹（与前端 executionTrace 对齐）。"""

from __future__ import annotations

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
    trace.setdefault("tools", []).append(entry)


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
