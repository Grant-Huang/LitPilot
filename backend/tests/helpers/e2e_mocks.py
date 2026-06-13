"""Minimal test utilities for literature pipeline E2E tests.

Only contains helper functions for constructing test data.
All external I/O (LLM, search, fetch) uses REAL services in live tests.
"""
from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Seed data helpers
# ---------------------------------------------------------------------------


def seed_corpus_hits(count: int = 3) -> list[dict[str, str]]:
    """Generate sample corpus fetch hits for pre-seeding a session.

    These are stored in SessionCorpus.fetch_hits and used by
    review_refine / query_corpus / short_answer scenarios.
    """
    return [
        {
            "title": f"Paper {i}: LLM Hallucination Detection Methods",
            "url": f"https://arxiv.org/abs/2401.{i:04d}",
            "snippet": (
                f"This paper presents novel approaches to detect hallucinations "
                f"in large language models. Paper {i} proposes a benchmark "
                f"dataset and evaluation framework for measuring hallucination rates."
            ),
        }
        for i in range(1, count + 1)
    ]


SEED_REVIEW_MARKDOWN = (
    "# 1. 导言\n\n"
    "近年来，大语言模型（LLM）在自然语言处理领域取得了显著进展，"
    "但其生成的幻觉（hallucination）问题引起了广泛关注 [1][2]。\n\n"
    "# 2. 幻觉检测方法\n\n"
    "当前主流的幻觉检测方法可以分为以下几类：\n"
    "- 基于事实核查的方法 [1]\n"
    "- 基于不确定性估计的方法 [2]\n"
    "- 基于自一致性的方法 [3]\n\n"
    "# 3. 综合讨论\n\n"
    "综上所述，幻觉检测仍是一个活跃的研究领域 [1][2][3]。\n"
)


# ---------------------------------------------------------------------------
# Event collection helpers
# ---------------------------------------------------------------------------


async def collect_turn_events(
    session_id: str,
    message: str,
    *,
    extra_fetch_urls: list[str] | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    """Collect all SSE events from stream_literature_turn.

    Catches exceptions from the pipeline (e.g., Turso constraint errors)
    and returns whatever events were collected before the error.
    """
    from app.agents.literature_turn import stream_literature_turn

    events: list[tuple[str, dict[str, Any]]] = []
    try:
        async for ev in stream_literature_turn(
            session_id,
            message,
            extra_fetch_urls=extra_fetch_urls,
        ):
            events.append(ev)
    except Exception as exc:
        # Record the error as a synthetic event so tests can inspect it
        events.append(("_uncaught_exception", {"message": str(exc), "type": type(exc).__name__}))
    return events


def find_event(
    events: list[tuple[str, dict[str, Any]]], event_type: str
) -> dict[str, Any] | None:
    """Find the first event of a given type."""
    for etype, payload in events:
        if etype == event_type:
            return payload
    return None


def find_all_events(
    events: list[tuple[str, dict[str, Any]]], event_type: str
) -> list[dict[str, Any]]:
    """Find all events of a given type."""
    return [p for etype, p in events if etype == event_type]


def _find_extension_events(
    events: list[tuple[str, dict[str, Any]]], name: str
) -> list[dict[str, Any]]:
    """Find all extension events whose inner ``name`` matches."""
    out: list[dict[str, Any]] = []
    for etype, payload in events:
        if etype == "extension" and isinstance(payload, dict):
            if payload.get("name") == name:
                out.append(payload.get("data", {}))
    return out


def summarize_events(events: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    """Aggregate an event stream into a compact report summary.

    Collects search hit counts, per-source counts, fetch ok/failed,
    relevance filter kept/rejected, clarification, errors, and artifact size.
    """
    summary: dict[str, Any] = {
        "intent": None,
        "defer_generate": None,
        "skip_web_search": None,
        "skip_fetch": None,
        "has_error": False,
        "errors": [],
        "has_uncaught_exception": False,
        "uncaught_exception": None,
        "has_clarification": False,
        "clarification_prompt": None,
        "clarification_options_count": 0,
        "has_clarification_timeout": False,
        "has_clarification_error": False,
        "search": {
            "total_hits_found": 0,
            "total_hits_taken": 0,
            "source_counts": {},
            "subtopics": [],
            "pass_count": 0,
            "queries": [],
        },
        "fetch": {"ok": 0, "failed": 0, "skipped": 0, "total": 0},
        "filter": {"kept": 0, "rejected": 0},
        "turn_end_summary": None,
        "has_turn_end": False,
        "artifact_chars": 0,
        "artifact_deltas": 0,
        "event_count": len(events),
        "stage_names": [],
    }

    for etype, payload in events:
        if not isinstance(payload, dict):
            continue

        if etype == "literature_intent":
            summary["intent"] = payload.get("intent")
            summary["defer_generate"] = payload.get("defer_generate")
            summary["skip_web_search"] = payload.get("skip_web_search")
            summary["skip_fetch"] = payload.get("skip_fetch")

        elif etype == "error":
            summary["has_error"] = True
            summary["errors"].append(payload.get("message", ""))

        elif etype == "_uncaught_exception":
            summary["has_uncaught_exception"] = True
            summary["uncaught_exception"] = {
                "message": payload.get("message", ""),
                "type": payload.get("type", ""),
            }

        elif etype == "clarification":
            summary["has_clarification"] = True
            summary["clarification_prompt"] = payload.get("prompt", "")
            opts = payload.get("options", [])
            summary["clarification_options_count"] = len(opts) if isinstance(opts, list) else 0

        elif etype == "clarification_timeout":
            summary["has_clarification_timeout"] = True

        elif etype == "clarification_error":
            summary["has_clarification_error"] = True

        elif etype == "literature_search_pass_done":
            search = summary["search"]
            search["total_hits_found"] += int(payload.get("hits_found", 0) or 0)
            search["total_hits_taken"] += int(payload.get("hits_taken", 0) or 0)
            search["pass_count"] += 1
            q = payload.get("query", "")
            if q:
                search["queries"].append(q)
            sc = payload.get("source_counts") or {}
            if isinstance(sc, dict):
                for src, cnt in sc.items():
                    search["source_counts"][src] = (
                        search["source_counts"].get(src, 0) + int(cnt or 0)
                    )

        elif etype == "literature_subtopic_plan":
            subs = payload.get("subtopics", [])
            if isinstance(subs, list):
                for sub in subs:
                    if isinstance(sub, dict):
                        summary["search"]["subtopics"].append(
                            {
                                "id": sub.get("id", ""),
                                "title": sub.get("title", ""),
                                "search_query": sub.get("search_query", ""),
                                "raw_count": None,
                                "kept_count": None,
                            }
                        )

        elif etype == "literature_subtopic_search_done":
            sid = payload.get("subtopic_id", "")
            raw = payload.get("raw_count", 0)
            for sub in summary["search"]["subtopics"]:
                if sub["id"] == sid:
                    sub["raw_count"] = raw
                    break

        elif etype == "literature_subtopic_filter_done":
            sid = payload.get("subtopic_id", "")
            kept = payload.get("kept_count", 0)
            rejected_list = payload.get("rejected", [])
            rejected_n = len(rejected_list) if isinstance(rejected_list, list) else 0
            summary["filter"]["kept"] += int(kept or 0)
            summary["filter"]["rejected"] += int(rejected_n or 0)
            for sub in summary["search"]["subtopics"]:
                if sub["id"] == sid:
                    sub["kept_count"] = kept
                    break

        elif etype == "literature_subtopic_fetch_done":
            fetch = summary["fetch"]
            fetch["ok"] += int(payload.get("ok", 0) or 0)
            fetch["failed"] += int(payload.get("failed", 0) or 0)
            fetch["skipped"] += int(payload.get("skipped", 0) or 0)

        elif etype == "stage":
            name = payload.get("name", "")
            state = payload.get("state", "")
            if name and state == "active" and name not in summary["stage_names"]:
                summary["stage_names"].append(name)

        elif etype == "artifact":
            delta = payload.get("delta", "")
            if delta:
                summary["artifact_chars"] += len(delta)
                summary["artifact_deltas"] += 1

        elif etype == "extension" and payload.get("name") == "turn_end":
            data = payload.get("data", {})
            summary["has_turn_end"] = True
            summary["turn_end_summary"] = data.get("summary", "")

    summary["fetch"]["total"] = (
        summary["fetch"]["ok"] + summary["fetch"]["failed"] + summary["fetch"]["skipped"]
    )
    return summary


def format_summary_text(summary: dict[str, Any]) -> str:
    """Format a summarize_events() result into a human-readable block."""
    lines: list[str] = []
    lines.append(f"intent={summary['intent']}  defer_generate={summary['defer_generate']}")
    lines.append(f"skip_web_search={summary['skip_web_search']}  skip_fetch={summary['skip_fetch']}")
    lines.append(f"events={summary['event_count']}  stages={summary['stage_names']}")

    if summary["has_error"]:
        lines.append(f"ERRORS: {summary['errors']}")
    if summary["has_uncaught_exception"]:
        ex = summary["uncaught_exception"]
        lines.append(f"UNCAUGHT: [{ex['type']}] {ex['message']}")

    if summary["has_clarification"] or summary["has_clarification_timeout"]:
        lines.append(
            f"CLARIFY: event={summary['has_clarification']} "
            f"timeout={summary['has_clarification_timeout']} "
            f"error={summary['has_clarification_error']} "
            f"options={summary['clarification_options_count']}"
        )
        if summary["clarification_prompt"]:
            lines.append(f"  prompt: {summary['clarification_prompt']}")

    search = summary["search"]
    lines.append(
        f"SEARCH: passes={search['pass_count']} "
        f"hits_found={search['total_hits_found']} "
        f"hits_taken={search['total_hits_taken']} "
        f"sources={search['source_counts']}"
    )
    for sub in search["subtopics"]:
        lines.append(
            f"  subtopic [{sub['id']}] {sub['title'][:40]} "
            f"raw={sub['raw_count']} kept={sub['kept_count']}"
        )

    fetch = summary["fetch"]
    flt = summary["filter"]
    lines.append(f"FETCH: ok={fetch['ok']} failed={fetch['failed']} skipped={fetch['skipped']} total={fetch['total']}")
    lines.append(f"FILTER: kept={flt['kept']} rejected={flt['rejected']}")
    lines.append(f"ARTIFACT: chars={summary['artifact_chars']} deltas={summary['artifact_deltas']}")
    lines.append(f"turn_end={summary['has_turn_end']}  summary={summary['turn_end_summary']!r}")
    return "\n".join(lines)
