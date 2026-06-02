"""Structured paper record for outline mount (AttributeTree lite)."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from app.library.canonical import canonical_key, normalize_url

ATTRIBUTE_KEYS: tuple[str, ...] = (
    "problem",
    "method",
    "datasets",
    "findings",
    "limitations",
    "keywords",
)


def make_paper_id(url: str) -> str:
    key = canonical_key(url=url) or normalize_url(url) or url.strip()
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


@dataclass
class PaperRecord:
    paper_id: str
    url: str
    title: str = ""
    library_id: str = ""
    bib_key: str = ""
    attri: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "paper_id": self.paper_id,
            "url": self.url,
            "title": self.title,
            "library_id": self.library_id,
            "bib_key": self.bib_key,
            "attri": dict(self.attri) if self.attri else {},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PaperRecord:
        attri_raw = data.get("attri")
        attri = dict(attri_raw) if isinstance(attri_raw, dict) else {}
        return cls(
            paper_id=str(data.get("paper_id") or ""),
            url=str(data.get("url") or ""),
            title=str(data.get("title") or ""),
            library_id=str(data.get("library_id") or ""),
            bib_key=str(data.get("bib_key") or ""),
            attri=attri,
        )

    def has_attri(self) -> bool:
        if not self.attri:
            return False
        return any(str(self.attri.get(k) or "").strip() for k in ATTRIBUTE_KEYS[:5])


def normalize_attri(raw: dict[str, Any] | None) -> dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}
    out: dict[str, Any] = {}
    for key in ATTRIBUTE_KEYS:
        val = src.get(key)
        if key == "keywords":
            if isinstance(val, list):
                out[key] = [str(v).strip() for v in val if str(v).strip()]
            elif isinstance(val, str) and val.strip():
                out[key] = [p.strip() for p in val.replace(",", " ").split() if p.strip()]
            else:
                out[key] = []
        else:
            out[key] = str(val or "").strip()
    return out
