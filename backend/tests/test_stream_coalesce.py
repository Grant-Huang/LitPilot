"""第二档：流式落库批处理与游标语义测试。"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from app.core.streaming import sse_event
from app.tasks.literature_tasks import COALESCE_MAX_CHARS, _StreamCoalescer
from app.tasks.task_store import FileTaskStore


def _collect():
    out: list[tuple[str, dict]] = []
    return out, lambda t, p: out.append((t, dict(p)))


def test_coalesce_merges_consecutive_same_type_deltas() -> None:
    out, flush = _collect()
    c = _StreamCoalescer(flush)
    for ch in ["a", "b", "c"]:
        c.add("text", {"delta": ch, "delivery": "chat"})
    c.flush()
    assert out == [("text", {"delta": "abc", "delivery": "chat"})]


def test_coalesce_preserves_full_content_no_token_loss() -> None:
    out, flush = _collect()
    c = _StreamCoalescer(flush)
    original = [f"t{i}" for i in range(50)]
    for d in original:
        c.add("text", {"delta": d, "delivery": "chat"})
    c.flush()
    merged = "".join(p["delta"] for _, p in out)
    assert merged == "".join(original)


def test_coalesce_flushes_on_char_threshold() -> None:
    out, flush = _collect()
    c = _StreamCoalescer(flush)
    big = "x" * (COALESCE_MAX_CHARS + 10)
    c.add("text", {"delta": big, "delivery": "chat"})
    assert len(out) == 1  # 超阈值立即 flush


def test_coalesce_different_signature_flushes_and_keeps_order() -> None:
    out, flush = _collect()
    c = _StreamCoalescer(flush)
    c.add("think", {"delta": "m1", "source": "model"})
    c.add("think", {"delta": "m2", "source": "model"})
    c.add("think", {"delta": "s1", "source": "system"})
    c.flush()
    assert out == [
        ("think", {"delta": "m1m2", "source": "model"}),
        ("think", {"delta": "s1", "source": "system"}),
    ]


def test_coalesce_non_coalescable_flushes_pending_first() -> None:
    out, flush = _collect()
    c = _StreamCoalescer(flush)
    c.add("text", {"delta": "ab", "delivery": "chat"})
    c.add("stage", {"name": "完成", "state": "done"})
    assert out[0] == ("text", {"delta": "ab", "delivery": "chat"})
    assert out[1] == ("stage", {"name": "完成", "state": "done"})


def test_coalesce_done_marker_not_merged() -> None:
    out, flush = _collect()
    c = _StreamCoalescer(flush)
    c.add("text", {"delta": "ab", "delivery": "chat"})
    c.add("text", {"delta": "", "delivery": "chat", "done": True})
    # done 标记不可合并：先 flush 前序增量，再立即下发 done
    assert out == [
        ("text", {"delta": "ab", "delivery": "chat"}),
        ("text", {"delta": "", "delivery": "chat", "done": True}),
    ]


def test_file_store_list_events_no_duplicates_across_polls() -> None:
    d = Path(tempfile.mkdtemp())
    store = FileTaskStore(root=d)
    task = store.create_task(session_id="s", message="m")
    for i in range(3):
        store.append_event(task.id, sse_event("text", {"delta": f"tok{i}"}))

    cursor = 0
    seen: list[str] = []
    for _ in range(5):
        evs = store.list_events(task.id, since=cursor)
        seen.extend(evs)
        cursor += len(evs)

    deltas = [json.loads(e[len("data: "):].strip())["payload"]["delta"] for e in seen]
    assert deltas == ["tok0", "tok1", "tok2"]


def test_file_store_incremental_read_picks_up_appends() -> None:
    d = Path(tempfile.mkdtemp())
    store = FileTaskStore(root=d)
    task = store.create_task(session_id="s", message="m")

    store.append_event(task.id, sse_event("text", {"delta": "a"}))
    first = store.list_events(task.id, since=0)
    assert len(first) == 1

    store.append_event(task.id, sse_event("text", {"delta": "b"}))
    second = store.list_events(task.id, since=1)
    assert len(second) == 1
    payload = json.loads(second[0][len("data: "):].strip())["payload"]
    assert payload["delta"] == "b"
