from __future__ import annotations

import time
from typing import Any, AsyncIterator, Literal

WorkflowNodeState = Literal["active", "done", "error", "skipped"]

NODE_PARENT: dict[str, str | None] = {
    "router": None,
    "search": "router",
    "fetch": "search",
    "cite_extract": "fetch",
    "generate": "cite_extract",
    "deliver": "generate",
}


def _now_ms() -> int:
    return int(time.time() * 1000)


class WorkflowNodeEmitter:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._started: dict[str, int] = {}

    def _payload(
        self,
        node_id: str,
        state: WorkflowNodeState,
        *,
        name: str | None = None,
        parent_id: str | None = None,
        started_at: int | None = None,
        duration_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "run_id": self.run_id,
            "node_id": node_id,
            "name": name or node_id,
            "state": state,
        }
        pid = parent_id if parent_id is not None else NODE_PARENT.get(node_id)
        if pid:
            body["parent_id"] = pid
        if started_at is not None:
            body["started_at"] = started_at
        if duration_ms is not None:
            body["duration_ms"] = duration_ms
        if metadata:
            body["metadata"] = metadata
        return body

    def event(
        self,
        node_id: str,
        state: WorkflowNodeState,
        *,
        name: str | None = None,
        parent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        started = self._started.get(node_id)
        dur: int | None = None
        if state in ("done", "error", "skipped") and started is not None:
            dur = _now_ms() - started
            self._started.pop(node_id, None)
        elif state == "active":
            self._started[node_id] = _now_ms()
            started = self._started[node_id]
        return (
            "workflow_node",
            self._payload(
                node_id,
                state,
                name=name,
                parent_id=parent_id,
                started_at=started,
                duration_ms=dur,
                metadata=metadata,
            ),
        )

    async def yield_begin(
        self,
        node_id: str,
        *,
        name: str | None = None,
        parent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        yield self.event(node_id, "active", name=name, parent_id=parent_id, metadata=metadata)

    async def yield_finish(
        self,
        node_id: str,
        state: WorkflowNodeState = "done",
        *,
        name: str | None = None,
        parent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        if node_id not in self._started:
            async for ev in self.yield_begin(
                node_id, name=name, parent_id=parent_id, metadata=metadata
            ):
                yield ev
        yield self.event(
            node_id, state, name=name, parent_id=parent_id, metadata=metadata
        )
