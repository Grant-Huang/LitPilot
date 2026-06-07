"""Decompose user brief into research sub-topics (M2)."""
from __future__ import annotations

import re
import uuid

from app.agents.literature_router import TOPIC_LABEL_MAX, clamp_search_query
from app.schemas.literature_outline import ResearchSubTopic

_CN_ENUM = re.compile(
    r"(?:^|\n)\s*"
    r"(?:其[一二三四五六七八]|第[一二三四五六七八]|(?:\(?[1-9]\d*\)?[\.、．]))"
    r"[，,、:\s]*"
    r"(.+?)(?=(?:\n\s*(?:其[一二三四五六七八]|第[一二三四五六七八]|(?:\(?[1-9]\d*\)?[\.、．]))|\Z))",
    re.S,
)

_POLLUTED_MARKERS = re.compile(
    r"其[一二三四五六七八]|文献综述.*包括|我要写|包括\d+个方面"
)

_LATIN_TOKEN_RE = re.compile(
    r'[a-zA-Z0-9"\']+(?:[-_.][a-zA-Z0-9"\']+)*',
)


def _slug_id(prefix: str = "thread") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _clean_chunk(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = re.sub(r"[。；;]+$", "", t)
    return t.strip()


def is_polluted_search_query(query: str) -> bool:
    """Detect router fallback or echoed user brief — unsuitable for web_search."""
    q = (query or "").strip()
    if not q:
        return False
    if len(q) > 120:
        return True
    if _POLLUTED_MARKERS.search(q):
        return True
    return False


def extract_compact_base_query(base_query: str) -> str:
    """Keep short planner/router query; drop echoed multi-aspect brief."""
    base = (base_query or "").strip()
    if not base or is_polluted_search_query(base):
        return ""
    return clamp_search_query(base, max_len=TOPIC_LABEL_MAX, fallback=base)


def latin_tokens_for_search(text: str) -> str:
    """Extract Latin/ASCII tokens from mixed zh/en text for academic API queries."""
    tokens = _LATIN_TOKEN_RE.findall(text or "")
    seen: set[str] = set()
    out: list[str] = []
    for token in tokens:
        key = token.lower()
        if key in seen:
            continue
        if len(token) < 2 and not token.isupper():
            continue
        seen.add(key)
        out.append(token)
    return " ".join(out)


def _append_latin_supplement(base: str, core: str) -> str:
    supplement = latin_tokens_for_search(core)
    if not supplement:
        return base[:200]
    base_lower = base.lower()
    extra = [t for t in supplement.split() if t.lower() not in base_lower.split()]
    if not extra:
        return base[:200]
    return f"{base} {' '.join(extra)}"[:200]


def build_subtopic_search_query(
    title: str,
    description: str,
    base_query: str = "",
) -> str:
    """Compact per-subtopic query — English/Latin only; zh title stays in topic_title."""
    compact_base = extract_compact_base_query(base_query)
    title_short = (title or "").strip()
    desc_short = (description or "").strip()[:160]
    core = title_short or desc_short[:100]

    if compact_base:
        if core:
            return _append_latin_supplement(compact_base, core)
        return compact_base[:200]
    return latin_tokens_for_search(core)[:200]


def _normalize_aspect_enumeration(msg: str) -> str:
    """Break inline 「。其二」same-line enumerations so aspect regex can split."""
    text = (msg or "").strip()
    if not text:
        return text
    text = re.sub(
        r"([：:])\s*(其[一二三四五六七八])",
        r"\1\n\2",
        text,
    )
    text = re.sub(
        r"([。；;])\s*(其[二三四五六七八])",
        r"\1\n\2",
        text,
    )
    text = re.sub(
        r"([。；;])\s*(第[二三四五六七八])",
        r"\1\n\2",
        text,
    )
    return text


def format_pass_query_label(query: str, *, max_len: int = 80) -> str:
    """Prefer query tail so multi-pass labels differ when prefix is shared."""
    q = (query or "").strip()
    if len(q) <= max_len:
        return q
    return "…" + q[-(max_len - 1) :]


def decompose_research_brief(user_message: str, *, base_query: str = "") -> list[ResearchSubTopic]:
    """Rule-based split for numbered/multi-aspect briefs (其一…其四 / 1. …)."""
    msg = _normalize_aspect_enumeration((user_message or "").strip())
    if not msg:
        return []

    chunks: list[str] = []
    for m in _CN_ENUM.finditer(msg):
        body = _clean_chunk(m.group(1))
        if len(body) >= 8:
            chunks.append(body)

    if len(chunks) < 2:
        return []

    topics: list[ResearchSubTopic] = []
    for i, chunk in enumerate(chunks, start=1):
        title = chunk.split("，")[0].split(",")[0].strip()
        if len(title) > 48:
            title = title[:45] + "…"
        search_q = build_subtopic_search_query(title, chunk, base_query)
        topics.append(
            ResearchSubTopic(
                id=_slug_id(f"thread{i}"),
                title=title or f"子主题 {i}",
                description=chunk,
                search_query=search_q,
            )
        )
    return topics


def default_single_sub_topic(user_message: str, search_query: str) -> ResearchSubTopic:
    compact = extract_compact_base_query(search_query)
    if compact:
        topic = compact
    else:
        topic = (user_message or "文献综述").strip()[:120]
    return ResearchSubTopic(
        id=_slug_id("thread"),
        title=topic[:48],
        description=user_message.strip()[:500],
        search_query=topic[:200],
    )
