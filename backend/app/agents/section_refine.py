"""Section-level refine (P0): target parsing and prior review reuse."""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas.literature_outline import LiteratureOutline, OutlineSection

_SECTION_ONLY_RE = re.compile(
    r"(?:只|仅|专门)?(?:重写|改写|修订|修改|润色|更新)"
    r"(?:第?\s*([0-9一二三四五六七八]+)\s*(?:章|节|部分)|"
    r"(?:其[一二三四五六七八]|第[一二三四五六七八]))",
    re.I,
)
_ASPECT_RE = re.compile(r"其([一二三四五六七八])")
_CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8}
_KEEP_OTHERS_RE = re.compile(r"其余|其他章|其它章|别的章|保留.*章", re.I)


def _aspect_index(token: str) -> int | None:
    t = (token or "").strip()
    if t.isdigit():
        return int(t)
    if len(t) == 1 and t in _CN_NUM:
        return _CN_NUM[t]
    return None


def _body_sections(outline: LiteratureOutline) -> list[OutlineSection]:
    return [s for s in outline.sections if s.id not in ("sec-intro", "sec-conclusion")]


def parse_refine_target_section_ids(
    user_message: str,
    outline: LiteratureOutline,
) -> list[str] | None:
    """
    Parse which outline sections to regenerate.

    Returns None → regenerate all sections.
    Returns non-empty list → only those section ids.
    """
    msg = (user_message or "").strip()
    if not msg or not outline.sections:
        return None

    body_secs = _body_sections(outline)
    if not body_secs:
        return None

    hits: set[str] = set()

    for m in _SECTION_ONLY_RE.finditer(msg):
        raw = m.group(1) or m.group(0)
        aspect = _ASPECT_RE.search(raw or "")
        if aspect:
            idx = _CN_NUM.get(aspect.group(1), 0)
        else:
            idx = _aspect_index(raw or "") or 0
        if 1 <= idx <= len(body_secs):
            hits.add(body_secs[idx - 1].id)

    for m in _ASPECT_RE.finditer(msg):
        if not _SECTION_ONLY_RE.search(msg) and not re.search(
            r"重写|改写|修订|修改|润色", msg, re.I
        ):
            continue
        idx = _CN_NUM.get(m.group(1), 0)
        if 1 <= idx <= len(body_secs):
            hits.add(body_secs[idx - 1].id)

    if not hits and re.search(r"重写|改写|修订|修改|润色|更新", msg, re.I):
        m_num = re.search(
            r"第?\s*([0-9一二三四五六七八]+)\s*(?:章|节|部分)",
            msg,
            re.I,
        )
        if m_num:
            idx = _aspect_index(m_num.group(1)) or 0
            if 1 <= idx <= len(body_secs):
                hits.add(body_secs[idx - 1].id)

    for sec in outline.sections:
        title_key = sec.title.strip()
        if len(title_key) >= 4 and title_key in msg:
            if re.search(r"重写|改写|修订|修改|润色|更新", msg, re.I):
                hits.add(sec.id)

    if hits:
        return sorted(hits, key=lambda sid: _section_order(outline, sid))

    if _KEEP_OTHERS_RE.search(msg) and re.search(
        r"重写|改写|修订|修改", msg, re.I
    ):
        for sec in body_secs:
            if sec.title[:6] in msg or f"第{sec.number}" in msg:
                hits.add(sec.id)
        if hits:
            return sorted(hits, key=lambda sid: _section_order(outline, sid))

    return None


def _section_order(outline: LiteratureOutline, section_id: str) -> int:
    for i, sec in enumerate(outline.sections):
        if sec.id == section_id:
            return i
    return 999


def _header_patterns(section: OutlineSection) -> list[re.Pattern[str]]:
    title = re.escape(section.title.strip())
    patterns: list[str] = []
    if section.id == "sec-intro":
        patterns.append(rf"^#\s+{title}\s*$")
    elif section.id == "sec-conclusion":
        patterns.append(rf"^##\s+{title}\s*$")
    else:
        num = re.escape(section.number)
        patterns.append(rf"^##\s+{num}\.\s+{title}\s*$")
        patterns.append(rf"^##\s+{title}\s*$")
    return [re.compile(p, re.M | re.I) for p in patterns]


def extract_section_bodies_from_review(
    review_text: str,
    outline: LiteratureOutline,
) -> dict[str, str]:
    """Map section_id → body markdown from a stitched review."""
    text = (review_text or "").strip()
    if not text:
        return {}

    headers: list[tuple[int, str, OutlineSection]] = []
    for sec in outline.sections:
        for pat in _header_patterns(sec):
            m = pat.search(text)
            if m:
                headers.append((m.start(), m.group(0), sec))
                break

    if not headers:
        return {}

    headers.sort(key=lambda x: x[0])
    out: dict[str, str] = {}
    for i, (start, header_line, sec) in enumerate(headers):
        body_start = start + len(header_line)
        body_end = headers[i + 1][0] if i + 1 < len(headers) else len(text)
        body = text[body_start:body_end].strip()
        if body:
            out[sec.id] = body
    return out


@dataclass
class SectionRefinePlan:
    """Which sections to LLM-regenerate vs reuse from prior review."""

    target_section_ids: list[str] | None
    prior_bodies: dict[str, str]
    revision_directives: str

    def should_regenerate(self, section_id: str) -> bool:
        if self.target_section_ids is None:
            return True
        return section_id in self.target_section_ids


def build_section_refine_plan(
    *,
    user_message: str,
    outline: LiteratureOutline,
    prior_review_text: str,
    gen_directives: str,
) -> SectionRefinePlan:
    prior_bodies = extract_section_bodies_from_review(prior_review_text, outline)
    target_ids = parse_refine_target_section_ids(user_message, outline)
    return SectionRefinePlan(
        target_section_ids=target_ids,
        prior_bodies=prior_bodies,
        revision_directives=(gen_directives or user_message or "").strip()[:800],
    )
