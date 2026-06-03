from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import httpx

ACADEMIC_SEARCH_DOMAINS: tuple[str, ...] = (
    "arxiv.org",
    "openreview.net",
    "aclanthology.org",
    "proceedings.neurips.cc",
    "proceedings.mlr.press",
    "jmlr.org",
    "dl.acm.org",
    "ieeexplore.ieee.org",
    "semanticscholar.org",
    "doi.org",
    "pubmed.ncbi.nlm.nih.gov",
    "pmc.ncbi.nlm.nih.gov",
    "biorxiv.org",
    "medrxiv.org",
    "ssrn.com",
    "link.springer.com",
    "nature.com",
    "science.org",
    "sciencedirect.com",
    "wiley.com",
    "frontiersin.org",
    "plos.org",
    "mdpi.com",
)

DEFAULT_EXCLUDE_DOMAINS: tuple[str, ...] = (
    "reddit.com",
    "github.com",
    "zhihu.com",
    "quora.com",
    "medium.com",
    "blog.csdn.net",
    "juejin.cn",
    "douban.com",
    "weibo.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "youtube.com",
    "bilibili.com",
)

_ZH_WRITING_JUNK_RE = re.compile(
    r"(?i)"
    r"(?:"  # 中文写作/教程/工具类噪声（对“学术综述”检索极易污染）
    r"文献综述\s*(?:怎么写|写作|写法|模板|结构|指南|教程|步骤|技巧)|"
    r"(?:怎么写|如何写|写作)\s*(?:文献综述|综述|论文)|"
    r"(?:AI|大模型|ChatGPT|GPT)\s*(?:写作|写论文|写综述|论文写作|文献综述)|"
    r"提示词|prompt|一键生成|生成器|润色|改写|降重|查重|写作助手|论文助手"
    r")"
)

_EN_WRITING_JUNK_RE = re.compile(
    r"(?i)"
    r"(?:"  # English “how to write a literature review” junk
    r"how\s+to\s+write\s+(?:a\s+)?literature\s+review|"
    r"literature\s+review\s+(?:guide|template|tips|steps)|"
    r"ai\s+writing|paper\s+writing\s+tool"
    r")"
)

_JUNK_TITLE_RE = re.compile(
    r"(?i)"
    r"(?:"
    r"url\s*source\s*:|"
    r"full\s+text\s+of\s+|"
    r"文献综述怎么写|"
    r"论文评述\]|"
    r"r/PhD|"
    r"convert\s+me\s+to\s+\.cit|"
    r"\$Id:\s*.*\.tit|"
    r"\.xlsx|"
    r"/eval/|"
    r"node_modules/"
    r")"
)

_JUNK_HOST_SUFFIXES = (
    "reddit.com",
    "github.com",
    "zhihu.com",
    "quora.com",
    "stackoverflow.com",
)

_MOM_MANUFACTURING_RE = re.compile(
    r"(?i)"
    r"(?:"
    r"ai[-\s]?native\s+mom|"
    r"制造运营|"
    r"制造执行|"
    r"\bMES\b|"
    r"\bMOM\b.*(?:制造|manufactur|shop\s*floor|ISA-?95)|"
    r"manufacturing\s+operations\s+management"
    r")"
)

_MOM_ML_FALSE_POSITIVE_RE = re.compile(
    r"(?i)mixture[-\s]?of[-\s]?memor",
)


def augment_literature_search_query(query: str) -> str:
    """Refine router output for Tavily — avoid Google site: operators."""
    q = query.strip()
    if not q:
        return q

    lower = q.lower()
    if _MOM_MANUFACTURING_RE.search(q):
        extras = []
        if "manufacturing operations management" not in lower:
            extras.append("manufacturing operations management")
        if "mes" not in lower and "制造执行" not in q:
            extras.append("MES manufacturing execution system")
        if "isa-95" not in lower:
            extras.append("ISA-95")
        if extras:
            q = f"{q} ({' '.join(extras)})"

    if not any(
        x in lower
        for x in (
            "survey",
            "systematic review",
            "literature review",
            "综述",
            "arxiv",
            "doi",
            "paper",
            "论文",
        )
    ):
        q = f"{q} academic survey peer-reviewed"

    return q[:500]


def filter_tavily_hits(hits: list[dict[str, str]]) -> list[dict[str, str]]:
    """Drop obvious non-paper URLs/titles after Tavily returns."""
    kept: list[dict[str, str]] = []
    for hit in hits:
        url = str(hit.get("url") or "").strip()
        title = str(hit.get("title") or "").strip()
        if not url:
            continue
        host = urlparse(url).netloc.lower()
        if any(host == sfx or host.endswith(f".{sfx}") for sfx in _JUNK_HOST_SUFFIXES):
            continue
        if _ZH_WRITING_JUNK_RE.search(title) or _ZH_WRITING_JUNK_RE.search(url):
            continue
        if _EN_WRITING_JUNK_RE.search(title) or _EN_WRITING_JUNK_RE.search(url):
            continue
        if _JUNK_TITLE_RE.search(title) or _JUNK_TITLE_RE.search(url):
            continue
        if _MOM_ML_FALSE_POSITIVE_RE.search(title):
            continue
        path = urlparse(url).path.lower()
        if path.endswith((".xlsx", ".json", ".csv", ".tit", ".aux", ".log")):
            continue
        kept.append(hit)
    return kept


def restrict_hits_to_domains(
    hits: list[dict[str, str]],
    *,
    include_domains: list[str] | tuple[str, ...] | None,
) -> list[dict[str, str]]:
    """Hard-enforce include_domains because upstream search may be loose."""
    if not include_domains:
        return hits
    allow = tuple(d.strip().lower() for d in include_domains if str(d).strip())
    if not allow:
        return hits
    kept: list[dict[str, str]] = []
    for h in hits:
        url = str(h.get("url") or "").strip()
        if not url:
            continue
        host = urlparse(url).netloc.lower()
        if any(host == d or host.endswith(f".{d}") for d in allow):
            kept.append(h)
    return kept


def apply_literature_hit_filters(
    raw_hits: list[dict[str, str]],
    *,
    include_domains: list[str] | tuple[str, ...] | None,
    enable_junk_filter: bool = True,
    enforce_domain_filter: bool = True,
) -> tuple[list[dict[str, str]], str | None]:
    """Apply junk + domain filters; relax domain filter when it removes all hits."""
    pre_count = len(raw_hits)
    hits = filter_tavily_hits(raw_hits) if enable_junk_filter else list(raw_hits)
    if not enforce_domain_filter or not include_domains:
        return hits, None
    domain_hits = restrict_hits_to_domains(hits, include_domains=include_domains)
    if domain_hits:
        return domain_hits, None
    if not hits:
        return hits, None
    warning = (
        f"学术域名过滤后无命中（原始 {pre_count} 条，去噪后 {len(hits)} 条），"
        "已保留去噪结果。"
    )
    return hits, warning


def build_tavily_search_payload(
    api_key: str,
    query: str,
    *,
    max_results: int = 8,
    search_depth: str = "advanced",
    include_domains: list[str] | tuple[str, ...] | None = None,
    exclude_domains: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": search_depth,
        "include_answer": True,
        "include_raw_content": False,
    }
    if include_domains:
        payload["include_domains"] = list(include_domains)
    merged_exclude = list(exclude_domains or ()) + [
        d for d in DEFAULT_EXCLUDE_DOMAINS if d not in (exclude_domains or ())
    ]
    if merged_exclude:
        payload["exclude_domains"] = merged_exclude
    return payload


async def tavily_search(
    api_key: str,
    query: str,
    *,
    max_results: int = 8,
    search_depth: str = "advanced",
    include_domains: list[str] | tuple[str, ...] | None = None,
    exclude_domains: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    if not api_key:
        raise ValueError("Tavily API Key 未配置")

    payload = build_tavily_search_payload(
        api_key,
        query,
        max_results=max_results,
        search_depth=search_depth,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
    )
    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.post("https://api.tavily.com/search", json=payload)
        resp.raise_for_status()
        return resp.json()


def normalize_tavily_results(data: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in data.get("results") or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        rows.append({
            "url": url,
            "title": str(item.get("title") or ""),
            "snippet": str(item.get("content") or "")[:800],
        })
    return rows
