"""Mutable context for end-of-turn persistence (corpus, trace, library)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.literature_intent import LiteratureIntentResult
from app.agents.session_corpus import SessionCorpus
from app.core.think_stream import ThinkAccumulator


@dataclass
class TurnFinalizeContext:
    store: Any
    session_id: str
    session_meta: dict[str, Any]
    session_title: str
    intent: LiteratureIntentResult
    user_message: str
    corpus: SessionCorpus
    execution_trace: dict[str, Any]
    think_acc: ThinkAccumulator
    fetch_results: list[tuple[dict[str, str], str, str | None]]
    cite_records: list[Any]
    failed_literature: list[dict[str, str]]
    gen_constraints: list[str]
    assistant_prefix: str = ""
