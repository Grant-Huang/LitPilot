"""v2 intent execution policy — what each intent runs."""
from __future__ import annotations

from app.agents.literature_intent import LiteratureIntentResult

SEARCH_INTENTS = frozenset({"new_topic", "subtopic_change"})
FETCH_INTENTS = frozenset({"new_topic", "subtopic_change", "append_urls"})
GENERATE_INTENTS = frozenset({"new_topic", "subtopic_change", "review_refine"})
CORPUS_ONLY_INTENTS = frozenset({"query_corpus", "append_urls"})


def runs_search(intent: LiteratureIntentResult) -> bool:
    if intent.skip_web_search:
        return False
    return intent.intent in SEARCH_INTENTS


def runs_fetch(intent: LiteratureIntentResult) -> bool:
    if intent.skip_fetch:
        return False
    return intent.intent in FETCH_INTENTS


def runs_generate(intent: LiteratureIntentResult) -> bool:
    if intent.defer_generate:
        return False
    return intent.intent in GENERATE_INTENTS


def is_corpus_turn(intent: LiteratureIntentResult) -> bool:
    return intent.intent in CORPUS_ONLY_INTENTS
