"""LLM relevance screening for merged search hits before web_fetch."""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.agents.llm_json import parse_json_object
from app.agents.url_list import title_from_search_hit
from app.core.think_stream import ThinkAccumulator, stream_llm_to_think
from app.llm.base import LLMMessage

_log = logging.getLogger(__name__)

RELEVANCE_SYSTEM = """你是学术文献相关性评审助手。根据【用户研究说明】与【检索式】，评估每条检索命中的相关程度。

评分（1-5）：
- 5：高度相关，应优先阅读
- 4：明确相关
- 3：边缘相关，可保留作背景
- 2：弱相关，与主题关联牵强
- 1：不相关或明显误检（领域/任务/对象不符）

规则：
- score >= 3 时 keep=true，否则 keep=false
- reason 用一句中文说明判断依据（20 字内为佳）
- 必须为每条输入输出 decisions 的一项，index 与输入列表 0-based 对齐

仅输出 JSON：
{
  "decisions": [{"index": 0, "score": 4, "keep": true, "reason": "..."}],
  "summary": "一句总体说明"
}"""

# 剔除比例 >= 50% 且候选 >= 4 篇时提示优化检索式
HIGH_REJECT_RATIO = 0.5
MIN_HITS_FOR_QUERY_WARN = 4
KEEP_SCORE_THRESHOLD = 3
BATCH_SIZE = 24


@dataclass
class RelevanceDecision:
    index: int
    score: int
    keep: bool
    reason: str
    title: str = ""
    url: str = ""


@dataclass
class RelevanceFilterResult:
    kept_hits: list[dict[str, str]]
    rejected: list[RelevanceDecision] = field(default_factory=list)
    input_count: int = 0
    kept_count: int = 0
    rejected_count: int = 0
    reject_ratio: float = 0.0
    query_warning: bool = False
    summary: str = ""
    llm_used: bool = False

    def to_report(self) -> dict[str, Any]:
        return {
            "input_count": self.input_count,
            "kept_count": self.kept_count,
            "rejected_count": self.rejected_count,
            "reject_ratio": round(self.reject_ratio, 3),
            "query_warning": self.query_warning,
            "summary": self.summary,
            "llm_used": self.llm_used,
            "rejected": [
                {
                    "title": d.title,
                    "url": d.url,
                    "score": d.score,
                    "reason": d.reason,
                }
                for d in self.rejected
            ],
        }


def _hit_label(hit: dict[str, str], *, index: int) -> str:
    url = str(hit.get("url") or "").strip()
    title = title_from_search_hit(hit, url=url)
    snippet = str(hit.get("snippet") or hit.get("content") or "").strip()
    line = f"[{index}] {title}"
    if snippet:
        line += f" — {snippet[:160]}"
    if url:
        line += f" ({url[:120]})"
    return line[:400]


def _normalize_decisions(
    raw: list[Any],
    *,
    batch_offset: int,
    hits: list[dict[str, str]],
) -> list[RelevanceDecision]:
    out: list[RelevanceDecision] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        idx = int(item.get("index", -1))
        if idx < 0 or idx >= len(hits):
            continue
        score = int(item.get("score") or 0)
        score = max(1, min(5, score))
        keep = bool(item.get("keep"))
        if score >= KEEP_SCORE_THRESHOLD:
            keep = True
        elif score < KEEP_SCORE_THRESHOLD:
            keep = False
        hit = hits[idx]
        url = str(hit.get("url") or "").strip()
        out.append(
            RelevanceDecision(
                index=batch_offset + idx,
                score=score,
                keep=keep,
                reason=str(item.get("reason") or "").strip()[:200],
                title=title_from_search_hit(hit, url=url),
                url=url,
            )
        )
    return out


def parse_relevance_json(
    raw: str,
    *,
    batch_offset: int,
    hits: list[dict[str, str]],
) -> tuple[list[RelevanceDecision], str]:
    data = parse_json_object(raw)
    decisions = _normalize_decisions(
        data.get("decisions") or [],
        batch_offset=batch_offset,
        hits=hits,
    )
    summary = str(data.get("summary") or "").strip()[:500]
    return decisions, summary


def apply_relevance_decisions(
    hits: list[dict[str, str]],
    decisions: list[RelevanceDecision],
) -> RelevanceFilterResult:
    decision_by_index = {d.index: d for d in decisions}
    kept: list[dict[str, str]] = []
    rejected: list[RelevanceDecision] = []

    for i, hit in enumerate(hits):
        dec = decision_by_index.get(i)
        if dec is None or dec.keep:
            kept.append(dict(hit))
        else:
            if dec and not dec.title:
                url = str(hit.get("url") or "").strip()
                dec.title = title_from_search_hit(hit, url=url)
                dec.url = url
            rejected.append(dec or RelevanceDecision(
                index=i,
                score=2,
                keep=False,
                reason="未评分，默认保留",
                title=title_from_search_hit(hit, url=str(hit.get("url") or "")),
                url=str(hit.get("url") or ""),
            ))

    # Fix: if dec is None we keep - good. If dec.keep false we reject.
    # If dec is None, we should keep without adding to rejected - fixed above

    input_count = len(hits)
    kept_count = len(kept)
    rejected_count = len(rejected)
    ratio = (rejected_count / input_count) if input_count else 0.0
    warn = (
        input_count >= MIN_HITS_FOR_QUERY_WARN
        and ratio >= HIGH_REJECT_RATIO
    )
    return RelevanceFilterResult(
        kept_hits=kept,
        rejected=rejected,
        input_count=input_count,
        kept_count=kept_count,
        rejected_count=rejected_count,
        reject_ratio=ratio,
        query_warning=warn,
        llm_used=True,
    )


def keep_all_hits(hits: list[dict[str, str]], *, summary: str = "") -> RelevanceFilterResult:
    n = len(hits)
    return RelevanceFilterResult(
        kept_hits=[dict(h) for h in hits],
        input_count=n,
        kept_count=n,
        rejected_count=0,
        reject_ratio=0.0,
        query_warning=False,
        summary=summary,
        llm_used=False,
    )


async def _run_filter_batches(
    hits: list[dict[str, str]],
    *,
    user_message: str,
    search_query: str,
    llm: Any,
    think_acc: ThinkAccumulator | None,
    yield_think: bool,
) -> AsyncIterator[tuple[str, Any]]:
    """Shared batch loop; yields think events when ``yield_think`` is True.

    ``yield_think=False`` matches the legacy single-shot ``filter_hits_by_relevance``
    path (consumed by tests that mock ``llm.chat``). ``yield_think=True`` re-yields
    think SSE events so the per-subtopic pipeline can pipe them to the front-end.
    """
    for batch_start in range(0, len(hits), BATCH_SIZE):
        batch = hits[batch_start : batch_start + BATCH_SIZE]
        lines = [_hit_label(h, index=i) for i, h in enumerate(batch)]
        prompt = (
            f"【用户研究说明】\n{(user_message or '').strip()[:2000]}\n\n"
            f"【检索式】\n{(search_query or '').strip()[:500]}\n\n"
            f"【待评估文献】共 {len(batch)} 条\n"
            + "\n".join(lines)
        )
        content_buf: list[str] = []
        async for ev in stream_llm_to_think(
            llm,
            [LLMMessage(role="user", content=prompt)],
            system=RELEVANCE_SYSTEM,
            accumulator=think_acc,
            max_tokens=1200,
            temperature=0.1,
            hide_json_in_stream=True,
            json_hide_hint="正在评估相关性…",
            content_buffer=content_buf,
        ):
            if yield_think:
                yield ev
        raw_text = "".join(content_buf)
        decisions, summary = parse_relevance_json(
            raw_text,
            batch_offset=batch_start,
            hits=batch,
        )
        if len(decisions) < len(batch):
            # 未全覆盖时：缺失条目默认保留
            covered = {d.index - batch_start for d in decisions}
            for i in range(len(batch)):
                if i not in covered:
                    hit = batch[i]
                    url = str(hit.get("url") or "").strip()
                    decisions.append(
                        RelevanceDecision(
                            index=batch_start + i,
                            score=KEEP_SCORE_THRESHOLD,
                            keep=True,
                            reason="模型未返回，默认保留",
                            title=title_from_search_hit(hit, url=url),
                            url=url,
                        )
                    )
        yield ("_batch_done", (decisions, summary))


def _aggregate_filter_results(
    hits: list[dict[str, str]],
    decisions: list[RelevanceDecision],
    summaries: list[str],
) -> RelevanceFilterResult:
    result = apply_relevance_decisions(hits, decisions)
    result.summary = "；".join(summaries)[:500]
    return result


async def filter_hits_by_relevance(
    hits: list[dict[str, str]],
    *,
    user_message: str,
    search_query: str,
    llm=None,
) -> RelevanceFilterResult:
    """Score merged search hits; drop low-relevance items.

    Synchronous path: keeps ``llm.chat`` so existing tests (which mock that
    method) continue to work. Streaming callers should use
    ``_filter_subtopic_hits_stream`` instead.
    """
    if not hits:
        return keep_all_hits([])

    if llm is None:
        return keep_all_hits(hits, summary="未配置 LLM，跳过相关性筛选")

    all_decisions: list[RelevanceDecision] = []
    summaries: list[str] = []

    for batch_start in range(0, len(hits), BATCH_SIZE):
        batch = hits[batch_start : batch_start + BATCH_SIZE]
        lines = [_hit_label(h, index=i) for i, h in enumerate(batch)]
        prompt = (
            f"【用户研究说明】\n{(user_message or '').strip()[:2000]}\n\n"
            f"【检索式】\n{(search_query or '').strip()[:500]}\n\n"
            f"【待评估文献】共 {len(batch)} 条\n"
            + "\n".join(lines)
        )
        try:
            resp = await llm.chat(
                [LLMMessage(role="user", content=prompt)],
                system=RELEVANCE_SYSTEM,
                max_tokens=1200,
                temperature=0.1,
            )
            decisions, summary = parse_relevance_json(
                resp.content or "",
                batch_offset=batch_start,
                hits=batch,
            )
            if len(decisions) < len(batch):
                # 未全覆盖时：缺失条目默认保留
                covered = {d.index - batch_start for d in decisions}
                for i in range(len(batch)):
                    if i not in covered:
                        hit = batch[i]
                        url = str(hit.get("url") or "").strip()
                        decisions.append(
                            RelevanceDecision(
                                index=batch_start + i,
                                score=KEEP_SCORE_THRESHOLD,
                                keep=True,
                                reason="模型未返回，默认保留",
                                title=title_from_search_hit(hit, url=url),
                                url=url,
                            )
                        )
            all_decisions.extend(decisions)
            if summary:
                summaries.append(summary)
        except Exception:
            _log.exception("relevance filter LLM batch failed")
            return keep_all_hits(
                hits,
                summary="相关性筛选失败，保留全部命中",
            )

    result = apply_relevance_decisions(hits, all_decisions)
    result.summary = "；".join(summaries)[:500]
    return result


async def _filter_subtopic_hits_stream(
    *,
    hits: list[dict[str, str]],
    user_message: str,
    search_query: str,
    llm: Any,
    think_acc: ThinkAccumulator | None,
) -> AsyncIterator[tuple[str, Any]]:
    """Per-subtopic LLM relevance filter that surfaces think SSE.

    Yields ``("think", {...})`` chunks emitted by ``stream_llm_to_think`` so the
    UI's think fold updates as the relevance filter streams reasoning content.
    The final ``("_filter_done", result)`` event carries the kept hits so the
    caller can drop them into the per-subtopic pipeline.
    """
    if not hits:
        yield ("_filter_done", RelevanceFilterResult(kept_hits=[]))
        return
    if llm is None:
        yield ("_filter_done", keep_all_hits(hits, summary="未配置 LLM，跳过相关性筛选"))
        return
    all_decisions: list[RelevanceDecision] = []
    summaries: list[str] = []
    failed = False
    try:
        async for ev in _run_filter_batches(
            hits,
            user_message=user_message,
            search_query=search_query,
            llm=llm,
            think_acc=think_acc,
            yield_think=True,
        ):
            if ev[0] == "think":
                yield ev
            elif ev[0] == "_batch_done":
                decisions, summary = ev[1]
                all_decisions.extend(decisions)
                if summary:
                    summaries.append(summary)
    except Exception:
        _log.exception("streaming relevance filter failed")
        failed = True

    if failed:
        result: RelevanceFilterResult = keep_all_hits(
            hits, summary="相关性筛选失败，保留全部命中"
        )
    else:
        result = _aggregate_filter_results(hits, all_decisions, summaries)
    yield ("_filter_done", result)


def format_reject_report_lines(result: RelevanceFilterResult) -> list[str]:
    lines: list[str] = []
    if result.input_count == 0:
        return lines
    lines.append(
        f"相关性筛选：{result.input_count} 篇 → 保留 {result.kept_count} 篇，"
        f"剔除 {result.rejected_count} 篇。"
    )
    if result.summary:
        lines.append(result.summary)
    for dec in result.rejected:
        title = (dec.title or dec.url or "Untitled")[:80]
        reason = dec.reason or "弱相关"
        lines.append(f"剔除 [{dec.score}] {title} — {reason}")
    if result.query_warning:
        pct = int(round(result.reject_ratio * 100))
        lines.append(
            f"⚠ 剔除比例 {pct}% 偏高，建议收窄检索式：补充领域/方法/对象关键词，"
            "或使用更具体的英文术语与同义词。"
        )
    return lines
