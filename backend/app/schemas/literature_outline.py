"""Literature outline schema (M2)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ResearchSubTopic:
    id: str
    title: str
    description: str
    search_query: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "search_query": self.search_query,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResearchSubTopic:
        return cls(
            id=str(data.get("id") or ""),
            title=str(data.get("title") or ""),
            description=str(data.get("description") or ""),
            search_query=str(data.get("search_query") or ""),
        )


@dataclass
class OutlineSection:
    id: str
    number: str
    title: str
    desc: str
    sub_topic_id: str = ""
    mounted_paper_ids: list[str] = field(default_factory=list)
    mount_hints: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "number": self.number,
            "title": self.title,
            "desc": self.desc,
            "sub_topic_id": self.sub_topic_id,
            "mounted_paper_ids": list(self.mounted_paper_ids),
            "mount_hints": list(self.mount_hints),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OutlineSection:
        hints = data.get("mount_hints") or []
        return cls(
            id=str(data.get("id") or ""),
            number=str(data.get("number") or ""),
            title=str(data.get("title") or ""),
            desc=str(data.get("desc") or ""),
            sub_topic_id=str(data.get("sub_topic_id") or ""),
            mounted_paper_ids=[str(x) for x in (data.get("mounted_paper_ids") or [])],
            mount_hints=[dict(h) for h in hints if isinstance(h, dict)],
        )


@dataclass
class LiteratureOutline:
    topic: str
    research_questions: list[str] = field(default_factory=list)
    sub_topics: list[ResearchSubTopic] = field(default_factory=list)
    sections: list[OutlineSection] = field(default_factory=list)
    status: str = "draft"

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "topic": self.topic,
            "research_questions": list(self.research_questions),
            "sub_topics": [s.to_dict() for s in self.sub_topics],
            "sections": [s.to_dict() for s in self.sections],
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> LiteratureOutline | None:
        if not data:
            return None
        return cls(
            topic=str(data.get("topic") or ""),
            research_questions=[str(q) for q in (data.get("research_questions") or [])],
            sub_topics=[
                ResearchSubTopic.from_dict(s)
                for s in (data.get("sub_topics") or [])
                if isinstance(s, dict)
            ],
            sections=[
                OutlineSection.from_dict(s)
                for s in (data.get("sections") or [])
                if isinstance(s, dict)
            ],
            status=str(data.get("status") or "draft"),
        )

    def section_by_id(self, section_id: str) -> OutlineSection | None:
        for sec in self.sections:
            if sec.id == section_id:
                return sec
        return None
