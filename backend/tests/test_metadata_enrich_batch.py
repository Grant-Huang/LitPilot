"""Tests for parallel metadata enrichment."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.library.metadata_enrich import enrich_records_parallel
from app.skills.citation_extractor import CitationRecord


@pytest.mark.asyncio
async def test_enrich_records_parallel() -> None:
    recs = [
        CitationRecord(
            title="Paper A",
            authors="A",
            year="2020",
            venue="",
            doi="10.1/a",
            url="https://a.com",
            success=True,
        ),
        CitationRecord(
            title="Paper B",
            authors="B",
            year="2021",
            venue="",
            doi="",
            url="https://b.com",
            success=True,
        ),
    ]

    def fake_build(rec: CitationRecord) -> dict:
        return {"citation_count": 1 if rec.doi else 0, "doi": rec.doi or "10.2/b"}

    with patch(
        "app.library.metadata_enrich.build_enrich_patch_for_record",
        side_effect=fake_build,
    ):
        patches = await enrich_records_parallel(recs, parallel=2)

    assert len(patches) == 2
    assert patches[0]["citation_count"] == 1
