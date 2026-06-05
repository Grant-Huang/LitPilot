"""Citation extraction — publisher routing + APA/ACM formatting."""

from __future__ import annotations



import logging

import re

from dataclasses import dataclass

from typing import Any, Literal, Optional

from urllib.parse import urlparse



from app.agents.tools.cached_tools import cached_web_fetch

from app.skills.citation_meta import (

    extract_doi_from_url,

    extract_highwire_citation_meta,

    fetch_semantic_scholar_metadata,

    looks_like_title,

    merge_metadata_layers,

    parse_author_tokens,

    publisher_api_metadata,

    sanitize_citation_fields,

)

from app.storage.file_store import get_store



_log = logging.getLogger(__name__)



CitationFormat = Literal["apa", "acm"]

SUPPORTED_CITATION_FORMATS: tuple[CitationFormat, ...] = ("apa", "acm")





def normalize_citation_format(fmt: str | None) -> CitationFormat:

    value = (fmt or "apa").strip().lower()

    if value in SUPPORTED_CITATION_FORMATS:

        return value  # type: ignore[return-value]

    return "apa"





@dataclass

class CitationRecord:

    title: str

    authors: str

    year: str

    venue: str

    doi: str

    url: str

    abstract: str = ""

    publisher: str = ""

    success: bool = False

    error: str = ""



    def to_apa(self, index: int) -> str:

        authors = self.authors or "Unknown"

        year = self.year or "n.d."

        title = self.title or "Untitled"

        venue = self.venue or ""

        doi_part = f" https://doi.org/{self.doi}" if self.doi else f" {self.url}"

        line = f"[{index}] {authors} ({year}). {title}."

        if venue:

            line += f" {venue}."

        line += doi_part.strip()

        return line



    def to_acm(self, index: int) -> str:

        authors = self.authors or "Unknown"

        year = self.year or "n.d."

        title = self.title or "Untitled"

        venue = self.venue or ""

        if self.doi:

            locator = f"DOI:https://doi.org/{self.doi}"

        else:

            locator = self.url

        line = f"[{index}] {authors}. {year}. {title}."

        if venue:

            line += f" {venue}."

        if locator:

            line += f" {locator}"

        return line.rstrip()



    def format_line(self, index: int, fmt: CitationFormat = "apa") -> str:

        if fmt == "acm":

            return self.to_acm(index)

        return self.to_apa(index)





def detect_publisher(url: str) -> str:

    host = urlparse(url).netloc.lower()

    if "arxiv.org" in host:

        return "arxiv"

    if "dblp.org" in host:

        return "dblp"

    if "acm.org" in host or "dl.acm.org" in host:

        return "acm"

    if "ieee" in host:

        return "ieee"

    if "semanticscholar.org" in host:

        return "semantic_scholar"

    if "sciencedirect" in host or "elsevier" in host:

        return "elsevier_blocked"

    if "researchgate" in host:

        return "researchgate_blocked"

    if "scholar.google" in host:

        return "google_scholar_blocked"

    return "generic"





def _next_ref_index() -> int:

    store = get_store()

    text = store.read_ref_list()

    nums = [int(m) for m in re.findall(r"^\[(\d+)\]", text, re.MULTILINE)]

    return max(nums, default=0) + 1





def _extract_year(text: str) -> str:

    m = re.search(r"\b(19|20)\d{2}\b", text)

    return m.group(0) if m else ""





def _extract_title_from_body(text: str, fallback: str = "") -> str:

    for pat in (

        r"^#\s+(.+)$",

        r"Title:\s*(.+)",

        r"<title[^>]*>([^<]+)</title>",

    ):

        m = re.search(pat, text, re.I | re.M)

        if m:

            cand = m.group(1).strip()[:300]

            if looks_like_title(cand):

                return cand

    lines = [ln.strip() for ln in text.splitlines() if 20 < len(ln.strip()) < 200]

    for ln in lines[:6]:

        if looks_like_title(ln):

            return ln[:300]

    fb = (fallback or "").strip()[:300]

    return fb if looks_like_title(fb) else ""





def _extract_authors_from_body(text: str) -> str:

    m = re.search(

        r"(?:Authors?|By)[:\s]+([^\n]{5,200})",

        text,

        re.I,

    )

    if m:

        raw = m.group(1).strip()[:200]

        tokens = parse_author_tokens(raw)

        if tokens:

            return ", ".join(tokens)

    return ""





def _extract_doi_from_body(text: str) -> str:

    m = re.search(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", text, re.I)

    return m.group(0) if m else ""





def _extract_abstract(text: str) -> str:

    m = re.search(

        r"(?im)^#+\s*abstract\s*$[\s\S]*?(?=^#+\s|\Z)",

        text,

    )

    if m:

        block = re.sub(r"^#+\s*abstract\s*", "", m.group(0), flags=re.I).strip()

        block = re.sub(r"\s+", " ", block)

        if len(block) > 60:

            return block[:2000]

    m2 = re.search(

        r"(?is)(?:^|\n)\s*abstract\s*[:\-]\s*(.+?)(?:\n\s*(?:keywords|introduction|1\.|index terms)|\Z)",

        text,

    )

    if m2:

        block = re.sub(r"\s+", " ", m2.group(1).strip())

        if len(block) > 60:

            return block[:2000]

    return ""





def _meta_dict_to_record_fields(meta: dict[str, Any]) -> dict[str, str]:

    authors_list = meta.get("authors")

    if isinstance(authors_list, list):

        authors = ", ".join(str(a) for a in authors_list if str(a).strip())

    else:

        authors = str(meta.get("authors") or "").strip()

    return {

        "title": str(meta.get("title") or "").strip(),

        "authors": authors,

        "year": str(meta.get("year") or "").strip(),

        "venue": str(meta.get("venue") or "").strip(),

        "doi": str(meta.get("doi") or "").strip(),

        "abstract": str(meta.get("abstract") or "").strip(),

        "publisher": str(meta.get("publisher") or "").strip(),

    }





async def _fetch_page_body(

    url: str,

    *,

    fetch_api_key: str | None,

    timeout: float,

) -> tuple[str, bool]:

    """Return (body, is_html). Prefer native HTML for citation meta tags."""

    try:

        from app.agents.agent_settings import get_web_fetch_provider

        from app.agents.tools.providers.native_fetch import fetch_bytes as native_fetch_bytes



        provider = await get_web_fetch_provider()

        if provider == "native" or not fetch_api_key:

            result = await native_fetch_bytes(

                url,

                timeout=timeout,

                s2_api_key=None,

            )

            body = result.text or ""

            sample = body[:4000].lower()

            is_html = (

                not result.is_pdf

                and ("<html" in sample or "<meta" in sample or "<head" in sample)

            )

            if body:

                return body, is_html

    except Exception:

        _log.debug("native fetch for citation failed, fallback", exc_info=True)



    body = await cached_web_fetch(url, api_key=fetch_api_key, timeout=timeout)

    sample = (body or "")[:4000].lower()

    is_html = "<html" in sample or "<meta" in sample

    return body, is_html





def _build_layers_from_body(

    body: str,

    *,

    is_html: bool,

    title_hint: str,

) -> list[dict[str, Any]]:

    layers: list[dict[str, Any]] = []

    if is_html:

        layers.append(extract_highwire_citation_meta(body))

    hint = (title_hint or "").strip()

    if hint and looks_like_title(hint):

        layers.append({"title": hint[:500]})

    layers.append(

        sanitize_citation_fields(

            {

                "title": _extract_title_from_body(body, hint),

                "authors": parse_author_tokens(_extract_authors_from_body(body)),

                "year": _extract_year(body),

                "doi": _extract_doi_from_body(body),

                "abstract": _extract_abstract(body),

            }

        )

    )

    return layers





def _record_from_merged(

    url: str,

    publisher: str,

    meta: dict[str, Any],

) -> CitationRecord:

    fields = _meta_dict_to_record_fields(meta)

    rec = CitationRecord(

        title=fields["title"],

        authors=fields["authors"],

        year=fields["year"],

        venue=fields["venue"],

        doi=fields["doi"],

        url=url,

        abstract=fields["abstract"],

        publisher=fields["publisher"] or publisher,

    )

    if publisher == "arxiv" and not rec.venue:

        rec.venue = "arXiv preprint"

    elif publisher == "acm" and not rec.venue:

        rec.venue = "ACM"

    elif publisher == "ieee" and not rec.venue:

        rec.venue = "IEEE"

    return rec





def _evaluate_success(rec: CitationRecord, publisher: str, url: str) -> None:

    has_scholarly_signal = bool(

        rec.doi

        or publisher in ("arxiv", "acm", "ieee", "semantic_scholar", "dblp")

        or re.search(r"arxiv\.org/(abs|pdf)/\d", url, re.I)

    )

    title_ok = bool(rec.title) and looks_like_title(rec.title)

    meta_ok = bool(rec.authors or rec.year)

    rec.success = bool(title_ok and meta_ok and has_scholarly_signal)

    if not rec.success:

        rec.error = "insufficient metadata"





async def extract_citation_from_url(

    url: str,

    *,

    fetch_api_key: str | None = None,

    title_hint: str = "",

    timeout: float = 60.0,

    s2_api_key: str | None = None,

) -> CitationRecord:

    publisher = detect_publisher(url)

    rec = CitationRecord(

        title=title_hint,

        authors="",

        year="",

        venue="",

        doi=extract_doi_from_url(url),

        url=url,

        publisher=publisher,

    )



    if publisher in ("elsevier_blocked", "researchgate_blocked", "google_scholar_blocked"):

        rec.error = f"publisher blocked: {publisher}"

        return rec



    layers: list[dict[str, Any]] = [publisher_api_metadata(url, publisher)]



    if publisher == "semantic_scholar":

        s2_patch = await fetch_semantic_scholar_metadata(

            url,

            api_key=s2_api_key,

            timeout=min(timeout, 25.0),

        )

        if s2_patch:

            layers.append(s2_patch)



    try:

        body, is_html = await _fetch_page_body(

            url,

            fetch_api_key=fetch_api_key,

            timeout=timeout,

        )

    except Exception as e:

        rec.error = str(e)

        if layers:

            merged = merge_metadata_layers(*layers)

            rec = _record_from_merged(url, publisher, merged)

            _evaluate_success(rec, publisher, url)

        return rec



    layers.extend(_build_layers_from_body(body, is_html=is_html, title_hint=title_hint))



    if not layers[-1].get("abstract"):

        paras = [p.strip() for p in body.split("\n\n") if len(p.strip()) > 80]

        if paras:

            layers.append({"abstract": paras[0][:500]})



    merged = merge_metadata_layers(*layers)

    rec = _record_from_merged(url, publisher, merged)

    _evaluate_success(rec, publisher, url)

    return rec





async def persist_citation(

    rec: CitationRecord,

    *,

    citation_format: CitationFormat = "apa",

    session_id: str = "",

    session_title: str = "",

) -> Optional[dict[str, Any]]:

    """Upsert into global library (deduped) and sync legacy ref-list."""

    if not rec.success:

        return None



    from app.library.upsert_citation import upsert_from_citation

    from app.library.from_run import _sync_exports

    from app.library.store import LibraryStore



    item = upsert_from_citation(

        rec,

        citation_format=citation_format,

        session_id=session_id,

        session_title=session_title,

    )

    if not item:

        return None

    _sync_exports(LibraryStore())

    return {

        "index": item.get("display_index"),

        "id": item.get("id"),

        "format": citation_format,

        "citation": (item.get("citations") or {}).get(citation_format),

        "apa": (item.get("citations") or {}).get("apa"),

        "title": item.get("title"),

        "authors": ", ".join(item.get("authors") or []),

        "year": item.get("year"),

        "url": item.get("url"),

        "doi": item.get("doi"),

        "publisher": item.get("publisher"),

    }





async def extract_and_persist_batch(

    hits: list[dict[str, str]],

    *,

    fetch_api_key: str | None = None,

    timeout: float = 60.0,

    max_items: int = 5,

    citation_format: CitationFormat = "apa",

    session_id: str = "",

    session_title: str = "",

) -> list[CitationRecord]:

    """Parallel cite extract, OpenAlex+Crossref enrich, then persist."""

    import asyncio



    from app.agents.agent_settings import get_fetch_parallel

    from app.library.metadata_enrich import enrich_records_parallel

    from app.library.upsert_citation import upsert_from_citation

    from app.library.from_run import _sync_exports

    from app.library.store import LibraryStore



    queue = hits[:max_items]

    if not queue:

        return []



    parallel = await get_fetch_parallel()

    extract_sem = asyncio.Semaphore(max(1, min(parallel, 8)))



    async def _extract_one(hit: dict[str, str]) -> CitationRecord:

        async with extract_sem:

            return await extract_citation_from_url(

                hit["url"],

                fetch_api_key=fetch_api_key,

                title_hint=hit.get("title") or "",

                timeout=timeout,

            )



    results: list[CitationRecord] = list(

        await asyncio.gather(*[_extract_one(h) for h in queue])

    )



    success_recs = [r for r in results if r.success]

    enrich_list: list[dict] = []

    if success_recs:

        enrich_list = await enrich_records_parallel(

            success_recs,

            parallel=parallel,

        )



    enrich_iter = iter(enrich_list)

    lib = LibraryStore()

    for rec in results:

        if not rec.success:

            continue

        ep = next(enrich_iter, {})

        upsert_from_citation(

            rec,

            lib=lib,

            citation_format=citation_format,

            session_id=session_id,

            session_title=session_title,

            enrich_patch=ep,

        )



    if success_recs:

        _sync_exports(lib)



    return results

