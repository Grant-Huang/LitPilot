"""Shared helpers for extracting JSON from LLM text output."""
from __future__ import annotations

import json
import re
from typing import Any

_JSON_OBJECT = re.compile(r"\{[\s\S]*\}")


def parse_json_object(raw: str) -> dict[str, Any]:
    """Extract and parse the first JSON object from model output."""
    text = (raw or "").strip()
    match = _JSON_OBJECT.search(text)
    if not match:
        raise ValueError("no JSON object in text")
    data = json.loads(match.group())
    if not isinstance(data, dict):
        raise ValueError("expected JSON object")
    return data
