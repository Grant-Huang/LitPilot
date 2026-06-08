"""Background literature turn tasks — persisted, multi-worker safe."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Callable

from app.agents.agent_skills import capabilities_payload
from app.agents.literature_workflow import stream_literature_turn
from app.core.streaming import normalize_chat_event, sse_event
from app.storage.file_store import get_store
from app.tasks.task_store import (
    TERMINAL_STATUSES,
    TaskRecord,
    get_task_store,
    get_worker_id,
)

logger = logging.getLogger(__name__)

STAGE_PROGRESS: dict[str, tuple[int, str]] = {
    "理解研究问题": (8, "understanding"),
    "Brief 评估": (12, "understanding"),
    "文献检索": (28, "searching"),
    "抓取网页": (42, "fetching"),
    "引用抽取": (52, "analyzing"),
    "综述生成": (78, "writing"),
    "矩阵生成": (78, "writing"),
    "文献问答": (78, "writing"),
    "后处理": (92, "writing"),
    "完成": (100, "completed"),
}

LIT_PROGRESS_STAGE: dict[str, tuple[int, str, int]] = {
    "understand": (5, "understanding", 8),
    "brief": (10, "understanding", 5),
    "search": (15, "searching", 30),
    "fetch": (42, "fetching", 12),
    "cite": (52, "analyzing", 10),
    "generate": (75, "writing", 20),
}

STREAM_POLL_SEC = 0.05
HEARTBEAT_SEC = 15.0
DEFAULT_SWEEP_SEC = 30
DEFAULT_STALE_SEC = 600

# 流式增量事件合并：把连续的同类 token 增量合并成一次落库，降低文件锁/DB 往返开销
COALESCE_TYPES = frozenset({"text", "think", "artifact"})
COALESCE_MAX_CHARS = 80


class _StreamCoalescer:
    """合并连续同类 token 增量后再落库，逐字 flush 改为按字符阈值/边界 flush。

    仅合并「纯增量」事件（``delta`` 字符串、未标记 ``done``、且除 ``delta`` 外的
    其余字段完全一致）。遇到不同签名/不可合并事件/结束时先 flush，保证顺序与
    前端按 delta 拼接的重建结果完全一致（不丢字、不串流）。
    """

    def __init__(self, flush: Callable[[str, dict[str, Any]], None]) -> None:
        self._flush_cb = flush
        self._type: str | None = None
        self._sig: tuple | None = None
        self._payload: dict[str, Any] | None = None
        self._parts: list[str] = []
        self._length = 0

    @staticmethod
    def _is_coalescable(ev_type: str, payload: dict[str, Any]) -> bool:
        return (
            ev_type in COALESCE_TYPES
            and isinstance(payload.get("delta"), str)
            and not payload.get("done")
        )

    @staticmethod
    def _signature(ev_type: str, payload: dict[str, Any]) -> tuple:
        rest = tuple(
            sorted(
                (k, json.dumps(v, ensure_ascii=False, sort_keys=True))
                for k, v in payload.items()
                if k != "delta"
            )
        )
        return (ev_type, rest)

    def add(self, ev_type: str, payload: dict[str, Any]) -> None:
        if not self._is_coalescable(ev_type, payload):
            self.flush()
            self._flush_cb(ev_type, payload)
            return

        sig = self._signature(ev_type, payload)
        if self._payload is not None and sig != self._sig:
            self.flush()
        if self._payload is None:
            self._type = ev_type
            self._sig = sig
            self._payload = dict(payload)
            self._parts = []
            self._length = 0
        delta = payload.get("delta", "")
        self._parts.append(delta)
        self._length += len(delta)
        if self._length >= COALESCE_MAX_CHARS:
            self.flush()

    def flush(self) -> None:
        if self._payload is None:
            return
        merged = dict(self._payload)
        merged["delta"] = "".join(self._parts)
        ev_type = self._type or "text"
        self._type = None
        self._sig = None
        self._payload = None
        self._parts = []
        self._length = 0
        self._flush_cb(ev_type, merged)


def _sweep_interval_sec() -> int:
    raw = os.getenv("LITPILOT_TASK_SWEEP_SEC", str(DEFAULT_SWEEP_SEC)).strip()
    try:
        return max(5, int(raw))
    except ValueError:
        return DEFAULT_SWEEP_SEC


def _stale_after_sec() -> int:
    raw = os.getenv("LITPILOT_TASK_STALE_SEC", str(DEFAULT_STALE_SEC)).strip()
    try:
        return max(60, int(raw))
    except ValueError:
        return DEFAULT_STALE_SEC


def _sweeper_enabled() -> bool:
    raw = os.getenv("LITPILOT_TASK_SWEEP_ENABLED", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


class LiteratureTaskRegistry:
    def __init__(self) -> None:
        self._store = get_task_store()
        self._local_runners: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()
        # 本地 runner 落库新事件时唤醒同进程的 SSE 消费端，避免固定轮询延迟
        self._event_signals: dict[str, asyncio.Event] = {}

    def _signal_for(self, task_id: str) -> asyncio.Event:
        sig = self._event_signals.get(task_id)
        if sig is None:
            sig = asyncio.Event()
            self._event_signals[task_id] = sig
        return sig

    def get(self, task_id: str) -> TaskRecord | None:
        return self._store.get_task(task_id)

    def list_active(self) -> list[TaskRecord]:
        return self._store.list_active_tasks()

    async def create_and_start(
        self,
        *,
        session_id: str,
        message: str,
        fetch_urls: list[str] | None = None,
    ) -> TaskRecord:
        record = self._store.create_task(
            session_id=session_id,
            message=message,
            fetch_urls=fetch_urls,
        )
        get_store().append_message(session_id, "user", message)
        await self._maybe_start_runner(record.id)
        refreshed = self._store.get_task(record.id)
        return refreshed or record

    async def _maybe_start_runner(self, task_id: str) -> None:
        worker_id = get_worker_id()
        if not self._store.try_claim(task_id, worker_id):
            return
        async with self._lock:
            if task_id in self._local_runners and not self._local_runners[task_id].done():
                return
            self._local_runners[task_id] = asyncio.create_task(self._run(task_id))

    async def cancel(self, task_id: str) -> TaskRecord | None:
        record = self._store.request_cancel(task_id)
        if not record:
            return None
        runner = self._local_runners.get(task_id)
        if runner and not runner.done():
            runner.cancel()
        if record.status in TERMINAL_STATUSES:
            return record
        finished = time.time()
        self._persist_event(task_id, "error", {"message": "任务已中止"})
        self._persist_event(task_id, "done", {})
        return self._store.update_task(
            task_id,
            status="cancelled",
            finished_at=finished,
        )

    def _progress_from_event(
        self,
        record: TaskRecord,
        event_type: str,
        payload: dict[str, Any],
    ) -> TaskRecord:
        progress = record.progress
        stage = record.stage
        if event_type == "stage":
            name = str(payload.get("name") or "")
            state = str(payload.get("state") or "")
            if name in STAGE_PROGRESS:
                prog, stage_key = STAGE_PROGRESS[name]
                if state == "done":
                    progress = max(progress, prog)
                elif state == "active":
                    progress = max(progress, max(0, prog - 6))
                stage = stage_key
        elif event_type == "extension":
            name = str(payload.get("name") or "")
            if name == "literature_progress":
                data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
                stage_key = str(data.get("stage") or "")
                if stage_key in LIT_PROGRESS_STAGE:
                    base, stage_key_name, span = LIT_PROGRESS_STAGE[stage_key]
                    stage = stage_key_name
                    completed = data.get("completed")
                    total = data.get("total")
                    if (
                        isinstance(completed, (int, float))
                        and isinstance(total, (int, float))
                        and total > 0
                    ):
                        ratio = min(1.0, max(0.0, float(completed) / float(total)))
                        progress = max(progress, base + int(span * ratio))
                    else:
                        progress = max(progress, base)
        record.progress = progress
        record.stage = stage
        return record

    def _persist_event(
        self,
        task_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        record = self._store.get_task(task_id)
        if not record:
            return
        prev_progress = record.progress
        prev_stage = record.stage
        record = self._progress_from_event(record, event_type, payload)
        line = sse_event(event_type, payload)
        self._store.append_event(task_id, line)
        # 仅在进度/阶段变化时写 meta，避免每个 token 都重写一次（append_event 已更新 updated_at）
        if record.progress != prev_progress or record.stage != prev_stage:
            self._store.update_task(
                task_id,
                progress=record.progress,
                stage=record.stage,
            )
        sig = self._event_signals.get(task_id)
        if sig is not None:
            sig.set()

    async def _run(self, task_id: str) -> None:
        record = self._store.get_task(task_id)
        if not record:
            return
        self._store.update_task(task_id, status="running", stage="starting")
        self._signal_for(task_id)
        coalescer = _StreamCoalescer(
            lambda t, p: self._persist_event(task_id, t, p)
        )
        try:
            self._persist_event(
                task_id,
                "extension",
                {
                    "name": "session",
                    "version": "1.0",
                    "data": {"session_id": record.session_id},
                },
            )
            self._persist_event(task_id, "capabilities", capabilities_payload())

            async for ev_type, payload in stream_literature_turn(
                record.session_id,
                record.message,
                extra_fetch_urls=record.fetch_urls or None,
                persist_user_message=False,
            ):
                if self._store.is_cancel_requested(task_id):
                    coalescer.flush()
                    finished = time.time()
                    self._persist_event(task_id, "error", {"message": "任务已中止"})
                    self._persist_event(task_id, "done", {})
                    self._store.update_task(
                        task_id,
                        status="cancelled",
                        finished_at=finished,
                    )
                    return

                for norm_type, norm_payload in normalize_chat_event(ev_type, payload):
                    coalescer.add(norm_type, norm_payload)

            coalescer.flush()
            current = self._store.get_task(task_id)
            if current and current.status == "running":
                self._persist_event(task_id, "done", {})
                self._store.update_task(
                    task_id,
                    status="completed",
                    progress=100,
                    stage="completed",
                    finished_at=time.time(),
                )
        except asyncio.CancelledError:
            coalescer.flush()
            current = self._store.get_task(task_id)
            if current and current.status not in TERMINAL_STATUSES:
                finished = time.time()
                self._persist_event(task_id, "error", {"message": "任务已中止"})
                self._persist_event(task_id, "done", {})
                self._store.update_task(
                    task_id,
                    status="cancelled",
                    finished_at=finished,
                )
            raise
        except ValueError as e:
            coalescer.flush()
            finished = time.time()
            self._persist_event(task_id, "error", {"message": str(e)})
            self._persist_event(task_id, "done", {})
            self._store.update_task(
                task_id,
                status="failed",
                error=str(e),
                finished_at=finished,
            )
        except Exception as e:
            logger.exception("literature task %s failed", task_id)
            coalescer.flush()
            finished = time.time()
            message = f"Error: {e}"
            self._persist_event(task_id, "error", {"message": message})
            self._persist_event(task_id, "done", {})
            self._store.update_task(
                task_id,
                status="failed",
                error=message,
                finished_at=finished,
            )
        finally:
            self._local_runners.pop(task_id, None)
            self._event_signals.pop(task_id, None)

    async def iter_stream(self, task_id: str, since: int = 0):
        cursor = max(0, since)
        last_activity = time.monotonic()
        while True:
            record = self._store.get_task(task_id)
            if not record:
                return
            events = self._store.list_events(task_id, since=cursor)
            for line in events:
                yield line
                cursor += 1
            if events:
                last_activity = time.monotonic()
            record = self._store.get_task(task_id)
            if not record or record.status in TERMINAL_STATUSES:
                return
            if not events:
                # 同进程 runner：事件信号唤醒（近零延迟）；跨进程：超时回退轮询
                sig = self._event_signals.get(task_id)
                if sig is not None:
                    try:
                        await asyncio.wait_for(sig.wait(), timeout=STREAM_POLL_SEC)
                    except asyncio.TimeoutError:
                        pass
                    sig.clear()
                else:
                    await asyncio.sleep(STREAM_POLL_SEC)
                # 长时间无事件时发送 SSE 注释心跳，避免代理/CDN 关闭空闲连接
                if time.monotonic() - last_activity >= HEARTBEAT_SEC:
                    yield ": keepalive\n\n"
                    last_activity = time.monotonic()

    async def sweep_once(self) -> None:
        """Requeue stale running tasks, then try to claim pending tasks."""
        cutoff = time.time() - _stale_after_sec()
        requeued = self._store.requeue_stale_running(cutoff)
        for task_id in requeued:
            logger.warning(
                "requeued stale literature task %s (no updates for %ss)",
                task_id,
                _stale_after_sec(),
            )
            runner = self._local_runners.get(task_id)
            if runner and not runner.done():
                runner.cancel()

        for task in self._store.list_active_tasks():
            if task.status != "pending":
                continue
            await self._maybe_start_runner(task.id)


_sweeper_task: asyncio.Task[None] | None = None
_registry: LiteratureTaskRegistry | None = None


async def _sweeper_loop() -> None:
    registry = get_task_registry()
    interval = _sweep_interval_sec()
    logger.info(
        "literature task sweeper started (interval=%ss stale=%ss)",
        interval,
        _stale_after_sec(),
    )
    while True:
        try:
            await registry.sweep_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("literature task sweeper tick failed")
        await asyncio.sleep(interval)


async def start_task_sweeper() -> None:
    global _sweeper_task
    if not _sweeper_enabled() or _sweeper_task is not None:
        return
    registry = get_task_registry()
    await registry.sweep_once()
    _sweeper_task = asyncio.create_task(_sweeper_loop())


async def stop_task_sweeper() -> None:
    global _sweeper_task
    if _sweeper_task is None:
        return
    _sweeper_task.cancel()
    try:
        await _sweeper_task
    except asyncio.CancelledError:
        pass
    _sweeper_task = None


def get_task_registry() -> LiteratureTaskRegistry:
    global _registry
    if _registry is None:
        _registry = LiteratureTaskRegistry()
    return _registry


def reset_task_registry_for_tests() -> None:
    global _registry, _sweeper_task
    _sweeper_task = None
    _registry = None
