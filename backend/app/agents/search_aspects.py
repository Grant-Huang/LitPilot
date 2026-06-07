"""Search aspect planning — per-source queries and exclude terms from Checkpoint A."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.agents.search_query_utils import SEARCH_QUERY_MAX, clamp_search_query
from app.schemas.literature_outline import ResearchSubTopic

SOURCE_ARXIV = "arxiv"
SOURCE_SEMANTIC_SCHOLAR = "semantic_scholar"
SOURCE_OPENALEX = "openalex"
SOURCE_CROSSREF = "crossref"
SOURCE_PUBMED = "pubmed"

DEFAULT_SEARCH_EXCLUDE_TERMS: tuple[str, ...] = (
    "municipal",
    "市政",
    "市政工程",
    "peer review process",
    "peer assessment at scale",
    "how to write",
    "literature review guide",
    "writing a literature review",
    "mental health operational model",
    "mixture-of-memor",
    "mixture of memor",
)

_OPENALEX_CROSSREF_KEYS = (
    "openalex_crossref_query",
    "openalexcrossref_query",
    "openalex_query",
    "crossref_query",
)


@dataclass
class SearchAspect:
    aspect_id: int
    aspect_label: str
    core_concepts: list[str] = field(default_factory=list)
    arxiv_query: str = ""
    semantic_scholar_query: str = ""
    openalex_crossref_query: str = ""
    pubmed_query: str = ""
    exclude_terms: list[str] = field(default_factory=list)

    def source_queries(self) -> dict[str, str]:
        shared = clamp_search_query(
            self.openalex_crossref_query,
            max_len=SEARCH_QUERY_MAX,
            fallback="",
        )
        out: dict[str, str] = {}
        mapping = {
            SOURCE_ARXIV: self.arxiv_query,
            SOURCE_SEMANTIC_SCHOLAR: self.semantic_scholar_query,
            SOURCE_OPENALEX: shared,
            SOURCE_CROSSREF: shared,
            SOURCE_PUBMED: self.pubmed_query,
        }
        for name, raw in mapping.items():
            q = clamp_search_query(str(raw or ""), max_len=SEARCH_QUERY_MAX, fallback="")
            if q:
                out[name] = q
        return out

    def primary_query(self) -> str:
        for candidate in (
            self.openalex_crossref_query,
            self.arxiv_query,
            self.semantic_scholar_query,
            self.pubmed_query,
        ):
            q = clamp_search_query(str(candidate or ""), max_len=SEARCH_QUERY_MAX, fallback="")
            if q:
                return q
        label = (self.aspect_label or "").strip()
        return clamp_search_query(label, max_len=SEARCH_QUERY_MAX, fallback=label)

    def skip_sources(self) -> frozenset[str]:
        if clamp_search_query(self.pubmed_query, fallback=""):
            return frozenset()
        return frozenset({SOURCE_PUBMED})

    def to_dict(self) -> dict[str, Any]:
        return {
            "aspect_id": self.aspect_id,
            "aspect_label": self.aspect_label,
            "core_concepts": list(self.core_concepts),
            "arxiv_query": self.arxiv_query,
            "semantic_scholar_query": self.semantic_scholar_query,
            "openalex_crossref_query": self.openalex_crossref_query,
            "pubmed_query": self.pubmed_query,
            "exclude_terms": list(self.exclude_terms),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SearchAspect | None:
        label = str(data.get("aspect_label") or "").strip()
        if not label:
            return None
        shared = ""
        for key in _OPENALEX_CROSSREF_KEYS:
            val = str(data.get(key) or "").strip()
            if val:
                shared = val
                break
        concepts = [
            str(c).strip()[:80]
            for c in (data.get("core_concepts") or [])
            if str(c).strip()
        ][:8]
        excludes = [
            str(t).strip().lower()[:120]
            for t in (data.get("exclude_terms") or [])
            if str(t).strip()
        ][:16]
        try:
            aspect_id = int(data.get("aspect_id") or 0)
        except (TypeError, ValueError):
            aspect_id = 0
        return cls(
            aspect_id=aspect_id,
            aspect_label=label[:120],
            core_concepts=concepts,
            arxiv_query=str(data.get("arxiv_query") or "").strip()[:SEARCH_QUERY_MAX],
            semantic_scholar_query=str(
                data.get("semantic_scholar_query") or ""
            ).strip()[:SEARCH_QUERY_MAX],
            openalex_crossref_query=shared[:SEARCH_QUERY_MAX],
            pubmed_query=str(data.get("pubmed_query") or "").strip()[:SEARCH_QUERY_MAX],
            exclude_terms=excludes,
        )


def _slug_id(prefix: str = "thread") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def parse_search_aspects(raw: Any) -> list[SearchAspect]:
    if not isinstance(raw, list):
        return []
    out: list[SearchAspect] = []
    for i, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            continue
        aspect = SearchAspect.from_dict(item)
        if not aspect:
            continue
        if not aspect.aspect_id:
            aspect.aspect_id = i
        if aspect.primary_query():
            out.append(aspect)
    return out


def aspects_to_sub_topics(aspects: list[SearchAspect]) -> list[ResearchSubTopic]:
    topics: list[ResearchSubTopic] = []
    for aspect in aspects:
        primary = aspect.primary_query()
        topics.append(
            ResearchSubTopic(
                id=_slug_id(f"thread{aspect.aspect_id or len(topics) + 1}"),
                title=aspect.aspect_label,
                description=" · ".join(aspect.core_concepts)[:500]
                or aspect.aspect_label,
                search_query=primary,
                source_queries=aspect.source_queries(),
                exclude_terms=list(aspect.exclude_terms),
            )
        )
    return topics


def merge_exclude_terms(*groups: list[str] | tuple[str, ...] | None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for group in groups:
        for item in group or ():
            s = str(item or "").strip().lower()
            if not s or s in seen:
                continue
            seen.add(s)
            out.append(s[:120])
    return out[:32]


def collect_search_exclusions(
    aspects: list[SearchAspect] | None = None,
    *,
    extra: list[str] | None = None,
) -> list[str]:
    aspect_terms: list[str] = []
    for aspect in aspects or []:
        aspect_terms.extend(aspect.exclude_terms)
    return merge_exclude_terms(
        DEFAULT_SEARCH_EXCLUDE_TERMS,
        aspect_terms,
        extra or [],
    )


def query_for_source(
    source: str,
    *,
    source_queries: dict[str, str],
    fallback: str,
) -> str:
    name = (source or "").strip().lower()
    direct = clamp_search_query(source_queries.get(name, ""), fallback="")
    if direct:
        return direct
    if name in (SOURCE_OPENALEX, SOURCE_CROSSREF):
        for key in (SOURCE_OPENALEX, SOURCE_CROSSREF, "openalex_crossref"):
            q = clamp_search_query(source_queries.get(key, ""), fallback="")
            if q:
                return q
    return clamp_search_query(fallback, max_len=SEARCH_QUERY_MAX, fallback=fallback)


def sub_topic_pass_spec(sub: ResearchSubTopic) -> tuple[str, dict[str, str], frozenset[str]]:
    """Return display query, per-source queries, and sources to skip."""
    fallback = clamp_search_query(sub.search_query, fallback=sub.title)
    source_queries = dict(sub.source_queries or {})
    if not source_queries and fallback:
        source_queries = {SOURCE_ARXIV: fallback, SOURCE_CROSSREF: fallback}
    skip: set[str] = set()
    if SOURCE_PUBMED not in source_queries:
        skip.add(SOURCE_PUBMED)
    return fallback, source_queries, frozenset(skip)
