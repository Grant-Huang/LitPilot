#!/usr/bin/env python3
"""Apply Turso schema migrations. Run from backend/: python scripts/turso_setup.py"""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from dotenv import load_dotenv

load_dotenv(BACKEND_ROOT.parent / ".env")
load_dotenv(BACKEND_ROOT / ".env")


def main() -> int:
    url = os.getenv("TURSO_DATABASE_URL", "").strip()
    if not url:
        print("ERROR: Set TURSO_DATABASE_URL in .env", file=sys.stderr)
        print("  turso db show <name> --url", file=sys.stderr)
        print("  turso db tokens create <name>", file=sys.stderr)
        return 1

    from app.storage.turso_db import apply_migrations, list_migration_files

    pending = list_migration_files()
    print(f"Turso URL: {url.split('@')[-1] if '@' in url else url}")
    print(f"Migration files: {[name for _, name, _ in pending]}")

    applied = apply_migrations()
    if applied:
        print("Applied:", ", ".join(applied))
    else:
        print("Schema already up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
