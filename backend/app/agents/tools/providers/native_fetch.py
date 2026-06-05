"""Direct HTTP web_fetch (native), inspired by docs/WebFetchTool."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urljoin, urlparse

import httpx

from app.agents.tools.pdf_text import pdf_bytes_to_text
from app.agents.tools.providers.jina import normalize_reader_target_url
from app.agents.tools.source_resolve import (
    is_pdf_bytes,
    is_pdf_content_type,
    resolve_fetch_url,
    resolve_pdf_from_html,
)

_MAX_BYTES = 10 * 1024 * 1024
_MAX_REDIRECTS = 10
_USER_AGENT = (
    "Mozilla/5.0 (compatible; LitPilot/1.0; +https://github.com/litpilot; academic fetch)"
)

_OJS_PDF_RE = re.compile(
    r'href=["\']([^"\']*/(?:article/download|viewFile)/[^"\']+)["\']',
    re.I,
)


@dataclass
class FetchResult:
    text: str
    final_url: str
    resolved_pdf_url: str | None = None
    is_pdf: bool = False


def _strip_www(host: str) -> str:
    return host[4:] if host.lower().startswith("www.") else host


def permitted_redirect(original: str, redirect: str) -> bool:
    try:
        a, b = urlparse(original), urlparse(redirect)
        if a.scheme != b.scheme or a.port != b.port:
            return False
        if b.username or b.password:
            return False
        return _strip_www(a.hostname or "") == _strip_www(b.hostname or "")
    except Exception:
        return False


def pick_ojs_pdf_url(html: str, page_url: str) -> str | None:
    resolved = resolve_pdf_from_html(html, page_url)
    if resolved:
        return resolved
    for m in _OJS_PDF_RE.finditer(html or ""):
        href = m.group(1).strip()
        if href:
            return urljoin(page_url, href)
    return None


def _default_headers() -> dict[str, str]:
    return {
        "Accept": "text/html,application/xhtml+xml,text/plain,application/pdf,*/*",
        "User-Agent": _USER_AGENT,
    }


async def fetch_bytes(
    url: str,
    *,
    timeout: float = 60.0,
    redirect_checker: Callable[[str, str], bool] | None = None,
    s2_api_key: str | None = None,
    pdf_extract_backend: str = "pypdf",
) -> FetchResult:
    """Fetch URL; resolve OJS / citation_pdf_url / S2 / PDF when possible."""
    target = normalize_reader_target_url(url)
    checker = redirect_checker or permitted_redirect
    headers = _default_headers()
    resolved_pdf_url: str | None = None

    parsed = urlparse(target)
    if not parsed.path.lower().endswith(".pdf"):
        try:
            better = await resolve_fetch_url(
                target,
                timeout=timeout,
                s2_api_key=s2_api_key,
            )
            if better and better != target:
                target = normalize_reader_target_url(better)
                if "download" in target.lower() or target.lower().endswith(".pdf"):
                    resolved_pdf_url = target
        except Exception:
            pass

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
    ) as client:
        current = target
        for _ in range(_MAX_REDIRECTS + 1):
            resp = await client.get(current, headers=headers)
            if resp.status_code in (301, 302, 307, 308):
                loc = resp.headers.get("location")
                if not loc:
                    resp.raise_for_status()
                nxt = urljoin(current, loc)
                if not checker(current, nxt):
                    break
                current = nxt
                continue
            resp.raise_for_status()
            raw = resp.content[:_MAX_BYTES]
            ctype = (resp.headers.get("content-type") or "").lower()
            final_url = str(resp.url)

            if is_pdf_content_type(ctype) or is_pdf_bytes(raw):
                text = pdf_bytes_to_text(raw, backend=pdf_extract_backend)
                return FetchResult(
                    text=text[:120_000],
                    final_url=final_url,
                    resolved_pdf_url=resolved_pdf_url or final_url,
                    is_pdf=True,
                )

            text = raw.decode(resp.encoding or "utf-8", errors="replace")
            if "text/html" in ctype or "<html" in text[:2000].lower():
                pdf = pick_ojs_pdf_url(text, final_url)
                if pdf and pdf != current:
                    resolved_pdf_url = pdf
                    current = normalize_reader_target_url(pdf)
                    continue
            return FetchResult(
                text=text[:120_000],
                final_url=final_url,
                resolved_pdf_url=resolved_pdf_url,
                is_pdf=False,
            )

    return FetchResult(text="", final_url=target, is_pdf=False)


async def fetch(
    url: str,
    *,
    timeout: float = 60.0,
    redirect_checker: Callable[[str, str], bool] | None = None,
    s2_api_key: str | None = None,
    pdf_extract_backend: str = "pypdf",
) -> str:
    """Fetch URL body as text/markdown-ish string (HTML decoded or PDF extracted)."""
    result = await fetch_bytes(
        url,
        timeout=timeout,
        redirect_checker=redirect_checker,
        s2_api_key=s2_api_key,
        pdf_extract_backend=pdf_extract_backend,
    )
    return result.text
