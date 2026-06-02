#!/usr/bin/env python3
"""Remove low-quality / non-scholarly entries from refs/library.json."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("LITPILOT_DATA_DIR", str(ROOT / "data"))

from app.agents.tools.tavily_search import filter_tavily_hits
from app.library.from_run import _sync_exports
from app.library.store import LibraryStore
from app.skills.citation_extractor import detect_publisher

_SCHOLARLY_PUBLISHERS = frozenset(
    {"arxiv", "acm", "ieee", "semantic_scholar", "dblp"}
)
_SCHOLARLY_HOST_FRAGMENTS = (
    "arxiv.org",
    "doi.org",
    "dl.acm.org",
    "ieeexplore.ieee.org",
    "semanticscholar.org",
    "openreview.net",
    "aclanthology.org",
    "proceedings.neurips.cc",
    "proceedings.mlr.press",
    "jmlr.org",
    "pubmed.ncbi.nlm.nih.gov",
    "pmc.ncbi.nlm.nih.gov",
    "link.springer.com",
    "nature.com",
    "science.org",
    "sciencedirect.com",
    "wiley.com",
    "frontiersin.org",
    "plos.org",
    "mdpi.com",
    "ssrn.com",
)

_TUTORIAL_TITLE_RE = re.compile(
    r"(?i)"
    r"(?:"
    r"文献综述怎么写|"
    r"如何写.*综述|"
    r"论文评述\]|"
    r"ai解课题|"
    r"教你怎么|"
    r"r/PhD"
    r")"
)


def _host(url: str) -> str:
    return urlparse(url).netloc.lower()


def is_noise_item(item: dict) -> bool:
    url = str(item.get("url") or "").strip()
    title = str(item.get("title") or "").strip()
    if not url:
        return True

    # 清理脚本不使用学术白名单收敛（避免误删），仅做噪声过滤
    if not filter_tavily_hits([{"url": url, "title": title, "snippet": ""}]):
        return True

    avail = item.get("availability") or {}
    if avail.get("cite_status") == "failed":
        return True

    if _TUTORIAL_TITLE_RE.search(title):
        return True

    host = _host(url)
    publisher = str(item.get("publisher") or detect_publisher(url))
    doi = str(item.get("doi") or "").strip()

    if publisher in _SCHOLARLY_PUBLISHERS:
        return False

    if doi and any(frag in host for frag in _SCHOLARLY_HOST_FRAGMENTS):
        return False

    if publisher == "generic":
        return True

    if doi and not any(frag in host for frag in _SCHOLARLY_HOST_FRAGMENTS):
        return True

  # Non-paper file extensions
    path = urlparse(url).path.lower()
    if path.endswith((".xlsx", ".json", ".csv", ".tit", ".aux", ".pdf")) and "arxiv" not in host:
        if not doi:
            return True

    return False


def main() -> int:
    lib = LibraryStore()
    items = lib.list_items()
    removed: list[str] = []
    kept: list[str] = []

    for item in items:
        iid = str(item.get("id") or "")
        label = (item.get("title") or item.get("url") or iid)[:80]
        if is_noise_item(item):
            if lib.delete_item(iid):
                removed.append(label)
        else:
            kept.append(label)

    _sync_exports(lib)

    print(f"data_dir={lib.root}")
    print(f"removed={len(removed)} kept={len(kept)}")
    for t in removed:
        print(f"  - {t}")
    if kept:
        print("kept:")
        for t in kept:
            print(f"  + {t}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
