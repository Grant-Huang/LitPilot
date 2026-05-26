from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from typing import Any, Generic, TypeVar

T = TypeVar("T")

DEFAULT_TTL_SEC = 600
DEFAULT_MAX_ENTRIES = 200


def normalize_cache_key(namespace: str, *parts: Any) -> str:
    normalized: list[str] = [namespace.strip().lower()]
    for p in parts:
        if isinstance(p, dict):
            normalized.append(
                json.dumps(p, sort_keys=True, ensure_ascii=False, default=str)
            )
        else:
            normalized.append(str(p).strip().lower())
    raw = "|".join(normalized)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TTLCache(Generic[T]):
    def __init__(self, *, max_entries: int = DEFAULT_MAX_ENTRIES, ttl_sec: int = DEFAULT_TTL_SEC):
        self._max = max_entries
        self._ttl = ttl_sec
        self._data: OrderedDict[str, tuple[float, T]] = OrderedDict()

    def get(self, key: str) -> T | None:
        entry = self._data.get(key)
        if not entry:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            del self._data[key]
            return None
        self._data.move_to_end(key)
        return value

    def set(self, key: str, value: T) -> None:
        expires_at = time.monotonic() + self._ttl
        self._data[key] = (expires_at, value)
        self._data.move_to_end(key)
        while len(self._data) > self._max:
            self._data.popitem(last=False)


tavily_cache: TTLCache[dict] = TTLCache()
jina_cache: TTLCache[str] = TTLCache()
