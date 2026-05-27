"""Literature review DAG: tavily → jina → cite_extract → LLM → deliver."""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, AsyncIterator

from app.agents.workflow_graph import NodeStatus, WorkflowGraph

MAX_SOURCE_CHARS = 14_000
WORKFLOW_ARTIFACT_LANG = "workflow-graph"
_log = logging.getLogger(__name__)

_CITATION_FORMAT_LABELS = {
    "apa": "APA",
    "acm": "ACM",
}


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _chunk_text(text: str, size: int = 28) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] if text else []


async def _emit_tool(
    name: str,
    args: dict[str, Any],
    output: str,
    *,
    error: str | None = None,
    duration_ms: int | None = None,
    trace: dict[str, Any] | None = None,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    tid = _new_id("tc")
    yield (
        "tool_call",
        {
            "id": tid,
            "name": name,
            "args": args,
            "risk": "safe",
            "provider": "api",
        },
    )
    payload: dict[str, Any] = {
        "tool_call_id": tid,
        "output": output if not error else "",
    }
    if error:
        payload["error"] = error
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms
    if trace is not None:
        append_tool(
            trace,
            tool_id=tid,
            name=name,
            args=args,
            status="error" if error else "done",
            output=output if not error else "",
            error=error,
            duration_ms=duration_ms,
        )
    yield ("tool_result", payload)


async def _emit_workflow_graph(
    graph: WorkflowGraph,
    graph_artifact_id: str,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    yield (
        "artifact",
        {
            "id": graph_artifact_id,
            "lang": WORKFLOW_ARTIFACT_LANG,
            "delta": graph.to_json(),
            "done": True,
        },
    )


async def _publish_workflow_graph(
    graph: WorkflowGraph,
    graph_artifact_id: str,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """Single full-graph snapshot (Meso artifact deltas are append-only)."""
    async for ev in _emit_workflow_graph(graph, graph_artifact_id):
        yield ev


async def _sync_graph_node(
    emitter: WorkflowNodeEmitter,
    graph: WorkflowGraph,
    graph_artifact_id: str,
    node_id: str,
    status: NodeStatus,
    *,
    parent_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    graph.set_node_status(node_id, status)
    if status == "active":
        async for ev in emitter.yield_begin(
            node_id, parent_id=parent_id, metadata=metadata
        ):
            yield ev
    elif status == "done":
        async for ev in emitter.yield_finish(
            node_id, "done", parent_id=parent_id, metadata=metadata
        ):
            yield ev
    elif status == "error":
        async for ev in emitter.yield_finish(
            node_id, "error", parent_id=parent_id, metadata=metadata
        ):
            yield ev


def _augment_query(user_message: str) -> str:
    q = user_message.strip()
    if not any(x in q.lower() for x in ("site:", "arxiv", "doi", "paper")):
        q = f"{q} (academic paper OR survey OR systematic review OR arXiv OR DOI)"
    return q


from app.agents.literature_turn import stream_literature_turn  # noqa: E402
