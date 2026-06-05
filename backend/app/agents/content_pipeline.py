from __future__ import annotations

import re
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup

from app.agents.tools.cached_tools import cached_web_fetch
from app.agents.prompt_registry import DEFAULT_SUMMARY_SYSTEM as SUMMARY_SYSTEM
from app.agents.prompt_settings import get_summary_system_prompt
from app.llm.base import LLMMessage

if TYPE_CHECKING:
    from app.llm.base import BaseLLM

CHUNK_SIZE = 3_200
MAX_CHUNKS = 6
MIN_USEFUL_CHARS = 80

_INSTRUCTION_PATTERNS = [
    re.compile(p, re.I | re.M)
    for p in (
        r"ignore\s+(all\s+)?(previous|above)\s+instructions",
        r"disregard\s+(prior|previous)",
        r"you\s+are\s+now\s+(a|an)\s+",
        r"system\s*:\s*",
        r"<\s*/?\s*system\s*>",
        r"jailbreak",
        r"忽略(以上|先前|之前).{0,12}指令",
    )
]

def clean_html_to_text(raw: str) -> str:
    if not raw or not raw.strip():
        return ""
    if "<" not in raw:
        return _collapse_ws(raw)
    soup = BeautifulSoup(raw, "lxml")
    for tag in soup(["script", "style", "noscript", "iframe", "svg", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    return _collapse_ws(text)


def extract_main_content(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ""
    kept: list[str] = []
    for ln in lines:
        if len(ln) < 3:
            continue
        if ln.count("|") > 8 and len(ln) < 120:
            continue
        kept.append(ln)
    body = "\n".join(kept)
    return body[:50_000]


def strip_instruction_injections(text: str) -> str:
    out = text
    for pat in _INSTRUCTION_PATTERNS:
        out = pat.sub("", out)
    return _collapse_ws(out)


def chunk_text(text: str, size: int = CHUNK_SIZE) -> list[str]:
    if len(text) <= size:
        return [text] if text.strip() else []
    chunks: list[str] = []
    start = 0
    while start < len(text) and len(chunks) < MAX_CHUNKS:
        chunks.append(text[start : start + size])
        start += size
    return chunks


def _collapse_ws(s: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", s)).strip()


async def summarize_chunks(llm: BaseLLM, chunks: list[str], *, url: str) -> str:
    summary_system = await get_summary_system_prompt()
    parts: list[str] = []
    for i, ch in enumerate(chunks, 1):
        resp = await llm.chat(
            [
                LLMMessage(
                    role="user",
                    content=f"来源 URL: {url}\n片段 {i}/{len(chunks)}:\n\n{ch[:CHUNK_SIZE]}",
                ),
            ],
            system=summary_system,
            max_tokens=600,
            temperature=0.1,
        )
        part = (resp.content or "").strip()
        if part:
            parts.append(part)
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    merge = await llm.chat(
        [
            LLMMessage(
                role="user",
                content="合并以下要点为一段 200 字以内的 Markdown 摘要，去重：\n\n"
                + "\n\n".join(parts),
            ),
        ],
        system=summary_system,
        max_tokens=500,
        temperature=0.1,
    )
    return (merge.content or "\n".join(parts)).strip()


async def process_url_for_context(
    url: str,
    *,
    api_key: str | None,
    llm: BaseLLM | None,
    fetch_timeout: float,
    title: str = "",
    fetch_provider: str | None = None,
) -> tuple[str, str | None]:
    try:
        raw = await cached_web_fetch(
            url,
            provider=fetch_provider,
            api_key=api_key,
            timeout=fetch_timeout,
        )
    except Exception as e:
        return "", str(e)

    inferred_title = ""
    if not title:
        # web_fetch（Jina Reader）通常会在开头给出 Markdown 标题（# Title）
        for ln in (raw or "").splitlines()[:30]:
            s = ln.strip()
            if s.startswith("# "):
                inferred_title = s[2:].strip()
                break
            if s.startswith("## "):
                inferred_title = s[3:].strip()
                break
        inferred_title = inferred_title[:200]

    text = clean_html_to_text(raw)
    text = extract_main_content(text)
    text = strip_instruction_injections(text)
    if len(text) < MIN_USEFUL_CHARS:
        return "", "content too short after filtering"

    final_title = (title or inferred_title).strip()

    if llm and len(text) > CHUNK_SIZE:
        chunks = chunk_text(text)
        summary = await summarize_chunks(llm, chunks, url=url)
        if summary:
            header = f"## {final_title or url}\n\n来源: {url}\n\n{summary}\n"
            return header, None

    header = f"## {final_title or url}\n\n来源: {url}\n\n{text[:14_000]}\n"
    return header, None
