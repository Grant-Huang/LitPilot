"""Batch test web_fetch + content_pipeline for a URL list file."""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

# backend root on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.content_pipeline import (
    MIN_USEFUL_CHARS,
    clean_html_to_text,
    extract_main_content,
    process_url_for_context,
    strip_instruction_injections,
)
from app.agents.tools.web_providers import web_fetch_url, web_fetch_url_with_meta


def load_urls(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    urls: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("http"):
            continue
        # fix truncated unicode ellipsis in file
        line = re.sub(r"\[…\]", "", line)
        if line not in seen:
            seen.add(line)
            urls.append(line)
    return urls


async def diagnose_url(url: str, provider: str) -> dict:
    out: dict = {"url": url, "provider": provider}
    try:
        meta = await web_fetch_url_with_meta(url, provider=provider, timeout=45.0)
        raw = str(meta.get("text") or "")
        out["raw_len"] = len(raw)
        out["final_url"] = meta.get("final_url")
        out["is_pdf"] = meta.get("is_pdf")
        out["resolved_pdf_url"] = meta.get("resolved_pdf_url")
        out["raw_preview"] = raw[:200].replace("\n", " ")
    except Exception as e:
        out["fetch_error"] = str(e)
        return out

    text = clean_html_to_text(raw)
    out["clean_len"] = len(text)
    main = extract_main_content(text)
    out["main_len"] = len(main)
    filtered = strip_instruction_injections(main)
    out["filtered_len"] = len(filtered)
    out["too_short"] = len(filtered) < MIN_USEFUL_CHARS
    out["main_preview"] = filtered[:200].replace("\n", " ")

    md, err = await process_url_for_context(
        url,
        api_key=None,
        llm=None,
        fetch_timeout=45.0,
        fetch_provider=provider,
    )
    out["pipeline_err"] = err
    out["pipeline_ok"] = bool(md)
    out["md_len"] = len(md or "")
    return out


async def main() -> None:
    url_file = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        r"d:\!OneDrive\OneDrive\Desktop\literature"
    )
    urls = load_urls(url_file)
    print(f"Loaded {len(urls)} unique URLs from {url_file}\n")

    for provider in ("native", "jina"):
        print("=" * 80)
        print(f"Provider: {provider}")
        print("=" * 80)
        ok = fail = 0
        for i, url in enumerate(urls, 1):
            r = await diagnose_url(url, provider)
            status = "OK" if r.get("pipeline_ok") else "FAIL"
            if r.get("pipeline_ok"):
                ok += 1
            else:
                fail += 1
            short_url = url[:70] + ("..." if len(url) > 70 else "")
            print(f"\n[{i}/{len(urls)}] {status} {short_url}")
            if r.get("fetch_error"):
                print(f"  fetch_error: {r['fetch_error']}")
            else:
                print(
                    f"  raw={r.get('raw_len', 0)} clean={r.get('clean_len', 0)} "
                    f"main={r.get('main_len', 0)} filtered={r.get('filtered_len', 0)} "
                    f"is_pdf={r.get('is_pdf')} min={MIN_USEFUL_CHARS}"
                )
                if r.get("final_url") and r["final_url"] != url:
                    print(f"  final_url: {r['final_url']}")
                if r.get("resolved_pdf_url"):
                    print(f"  pdf: {r['resolved_pdf_url']}")
                if r.get("pipeline_err"):
                    print(f"  pipeline_err: {r['pipeline_err']}")
                if r.get("too_short"):
                    print(f"  raw_preview: {r.get('raw_preview', '')[:120]}")
        print(f"\nSummary ({provider}): OK={ok} FAIL={fail}/{len(urls)}")


if __name__ == "__main__":
    asyncio.run(main())
