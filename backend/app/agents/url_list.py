"""Parse URL lists from user upload / API payload."""
from __future__ import annotations

import csv
import io
import json
import re
from typing import Any
from urllib.parse import urlparse

_URL_IN_TEXT = re.compile(r"https?://[^\s<>'\"]+", re.IGNORECASE)
_MAX_REQUEST_URLS = 50


def _normalize_url(raw: str) -> str | None:
    u = (raw or "").strip().strip(",;")
    if not u:
        return None
    if not u.startswith(("http://", "https://")):
        if u.startswith("www."):
            u = f"https://{u}"
        else:
            return None
    parsed = urlparse(u)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    return u.rstrip(".,;)")


def parse_urls_from_text(text: str) -> list[str]:
    found = [_normalize_url(m) for m in _URL_IN_TEXT.findall(text or "")]
    return _dedupe_urls([u for u in found if u])


def parse_urls_from_lines(text: str) -> list[str]:
    urls: list[str] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "http://" in line.lower() or "https://" in line.lower():
            urls.extend(parse_urls_from_text(line))
            continue
        for cell in re.split(r"[\t,;|]", line):
            u = _normalize_url(cell)
            if u:
                urls.append(u)
    return _dedupe_urls(urls)


def parse_urls_from_csv(text: str) -> list[str]:
    urls: list[str] = []
    reader = csv.reader(io.StringIO(text))
    for row in reader:
        for cell in row:
            u = _normalize_url(cell)
            if u:
                urls.append(u)
            else:
                urls.extend(parse_urls_from_text(cell))
    return _dedupe_urls(urls)


def parse_urls_from_json(text: str) -> list[str]:
    data = json.loads(text)
    urls: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, str):
            u = _normalize_url(node)
            if u:
                urls.append(u)
            else:
                urls.extend(parse_urls_from_text(node))
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            for key in ("url", "link", "href", "urls", "links"):
                if key in node:
                    walk(node[key])
            for v in node.values():
                if isinstance(v, (list, dict)):
                    walk(v)

    walk(data)
    return _dedupe_urls(urls)


def parse_url_list_file(content: str, *, filename: str = "") -> list[str]:
    name = (filename or "").lower()
    text = content or ""
    if name.endswith(".json"):
        try:
            return parse_urls_from_json(text)
        except json.JSONDecodeError:
            pass
    if name.endswith(".csv"):
        return parse_urls_from_csv(text)
    line_urls = parse_urls_from_lines(text)
    if line_urls:
        return line_urls
    return parse_urls_from_text(text)


def sanitize_fetch_urls(urls: list[str] | None, *, max_items: int = _MAX_REQUEST_URLS) -> list[str]:
    if not urls:
        return []
    out: list[str] = []
    for raw in urls:
        u = _normalize_url(str(raw))
        if u and u not in out:
            out.append(u)
        if len(out) >= max_items:
            break
    return out


def _dedupe_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def merge_fetch_hits(
    tavily_hits: list[dict[str, str]],
    extra_urls: list[str],
    *,
    max_urls: int,
) -> tuple[list[dict[str, str]], int]:
    """Prioritize user URLs, then Tavily hits. Returns (queue, extra_count)."""
    seen: set[str] = set()
    merged: list[dict[str, str]] = []
    extra_count = 0

    for url in extra_urls:
        if url in seen:
            continue
        seen.add(url)
        merged.append({
            "url": url,
            "title": "",
            "snippet": "",
            "source": "upload",
        })
        extra_count += 1
        if len(merged) >= max_urls:
            return merged, extra_count

    for hit in tavily_hits:
        url = str(hit.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        row = dict(hit)
        row.setdefault("source", "tavily")
        merged.append(row)
        if len(merged) >= max_urls:
            break

    return merged, extra_count


def resolve_fetch_display_title(hit: dict[str, str], ctx_md: str = "") -> str:
    """用于 UI 展示的文章标题（不用域名冒充标题）。"""
    url = str(hit.get("url") or "").strip()
    title = str(hit.get("title") or "").strip()
    if title and title != url:
        return title[:200]

    if ctx_md:
        # 兼容两种 header：
        # - 旧格式：## [网页材料] Title
        # - 新格式：## Title
        for pat in (
            r"^##\s*\[网页材料\]\s*(.+?)\s*$",
            r"^##\s+(.+?)\s*$",
        ):
            m = re.search(pat, ctx_md.strip(), re.MULTILINE)
            if not m:
                continue
            cand = m.group(1).strip()
            if cand and cand != url and not cand.lower().startswith("http"):
                return cand[:200]

    snippet = str(hit.get("snippet") or "").strip()
    if snippet:
        first = snippet.split("\n")[0].strip()
        if len(first) >= 12 and not first.lower().startswith("http"):
            return first[:160]

    return ""


def effective_fetch_cap(base_max: int, extra_urls: list[str]) -> int:
    from app.agents.agent_settings import MAX_FETCH_URLS_CAP

    if not extra_urls:
        return min(base_max, MAX_FETCH_URLS_CAP)
    return min(max(base_max, len(extra_urls)), MAX_FETCH_URLS_CAP)
