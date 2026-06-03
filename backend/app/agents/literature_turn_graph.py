"""Workflow graph artifact publishing and node status sync."""
from __future__ import annotations

from typing import Any, AsyncIterator

from app.agents.workflow_emitter import WorkflowNodeEmitter

WORKFLOW_ARTIFACT_LANG = "workflow-graph"


async def publish_workflow_graph(
    graph,
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


async def sync_graph_node(
    emitter: WorkflowNodeEmitter,
    graph,
    graph_artifact_id: str,
    node_id: str,
    status: str,
    *,
    parent_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    del graph_artifact_id  # kept for callback signature compatibility
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
    elif status == "skipped":
        async for ev in emitter.yield_finish(
            node_id, "skipped", parent_id=parent_id, metadata=metadata
        ):
            yield ev
