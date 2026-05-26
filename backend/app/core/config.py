"""Application configuration from environment."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = Path(os.getenv("LITPILOT_DATA_DIR", str(ROOT_DIR / "data"))).resolve()
