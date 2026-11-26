"""Mocked tests for live retrieval components; no real network calls."""

import pytest

from backend.services.chunking import chunk_text
from backend.services.retrieval import reciprocal_rank_fusion
from backend.services.search_providers import TavilySearchProvider, SearchProviderError
from backend.services.gemini_verdict import AtomicVerdictResult


def test_chunking_is_overlapping_and_preserves_offsets():
    text = "0123456789abcdefghij"
    chunks = chunk_text(text, chunk_size=10, overlap=2)
    assert chunks[0] == ("0123456789", 0, 10)
    assert chunks[1][1] == 8
    assert chunks[1][2] <= len(text)


def test_chunking_rejects_invalid_overlap():
    with pytest.raises(ValueError):
        chunk_text("hello world", chunk_size=5, overlap=5)


def test_reciprocal_rank_fusion_documented_aggregate():
    scores = reciprocal_rank_fusion([["a", "b"], ["b", "a"]])
    assert scores["a"] == scores["b"]


def test_tavily_provider_requires_key():
    with pytest.raises(SearchProviderError, match="TAVILY_API_KEY"):
        TavilySearchProvider(api_key="")


def test_insufficient_verdict_can_be_cited_as_no_passages():
    result = AtomicVerdictResult(
        label="INSUFFICIENT_EVIDENCE",
        confidence=0.0,
        explanation="No readable retrieved evidence was available.",
        supporting_passage_ids=[],
        refuting_passage_ids=[],
        cited_source_urls=[],
        limitations="No source text could be extracted.",
    )
    assert result.label == "INSUFFICIENT_EVIDENCE"


def test_verdict_rejects_confidence_out_of_range():
    with pytest.raises(Exception):
        AtomicVerdictResult(
            label="SUPPORTED",
            confidence=1.5,
            explanation="Test",
        )
