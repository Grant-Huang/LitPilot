"""Smoke tests for literature turn module split."""
from __future__ import annotations


def test_literature_turn_module_exports() -> None:
    from app.agents.literature_turn import stream_literature_turn
    from app.agents.literature_turn_generate import GenerateTurnContext, stream_generate_turn
    from app.agents.literature_turn_pipeline import RetrievalPipelineContext, run_retrieval_pipeline
    from app.agents.literature_workflow import stream_literature_turn as legacy

    assert stream_literature_turn is legacy
    assert callable(stream_generate_turn)
    assert callable(run_retrieval_pipeline)
    assert RetrievalPipelineContext.__name__ == "RetrievalPipelineContext"
    assert GenerateTurnContext.__name__ == "GenerateTurnContext"
