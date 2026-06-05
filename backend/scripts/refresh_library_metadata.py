#!/usr/bin/env python3
"""Re-enrich all library items from Crossref/OpenAlex and rebuild citation lines."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("LITPILOT_DATA_DIR", str(ROOT / "data"))


async def main() -> int:
    from app.library.metadata_enrich import refresh_library_metadata
    from app.library.store import LibraryStore

    parser = argparse.ArgumentParser(description="Refresh library metadata from Crossref")
    parser.add_argument("--parallel", type=int, default=4)
    args = parser.parse_args()

    lib = LibraryStore()
    stats = await refresh_library_metadata(lib, parallel=args.parallel)
    print(f"data_dir={lib.root}")
    print(
        f"updated={stats['updated']} skipped={stats['skipped']} total={stats['total']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
