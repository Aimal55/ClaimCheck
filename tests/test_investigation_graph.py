"""Tests for LangGraph construction and quality retry behavior."""

from backend.services.investigation_graph import (
    INVESTIGATION_GRAPH,
    quality_route,
)


def test_compiled_graph_is_available():
    assert INVESTIGATION_GRAPH is not None


def test_weak_evidence_routes_to_one_bounded_retry():
    state = {"weak_claims": ["claim-1"], "retry_count": 0}
    assert quality_route(state) == "search_sources"


def test_retry_limit_routes_to_finalization():
    state = {"weak_claims": ["claim-1"], "retry_count": 1}
    assert quality_route(state) == "finalize_investigation"


def test_strong_evidence_routes_to_finalization():
    state = {"weak_claims": [], "retry_count": 0}
    assert quality_route(state) == "finalize_investigation"
