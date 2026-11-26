"""Mocked tests for Gemini atomic claim decomposition; no real API calls."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.core.config import settings
from backend.schemas.claim import ClaimSubmission
from backend.services.gemini_service import (
    DecompositionResponse,
    GeminiDecompositionService,
    GeminiProviderError,
    MalformedGeminiOutputError,
    MissingGeminiAPIKeyError,
)


class MockModels:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error

    def generate_content(self, **kwargs):
        if self.error:
            raise self.error
        return self.response


class MockGeminiClient:
    def __init__(self, response=None, error=None):
        self.models = MockModels(response=response, error=error)


def test_missing_api_key():
    with pytest.raises(MissingGeminiAPIKeyError, match="GEMINI_API_KEY"):
        GeminiDecompositionService(api_key="", model="test-model")


def test_valid_response_parsed_by_pydantic():
    payload = DecompositionResponse.model_validate(
        {
            "claims": [
                {
                    "id": "claim-1",
                    "text": "The Eiffel Tower is 330 metres tall.",
                    "claim_type": "historical_measurement",
                    "entities": ["Eiffel Tower"],
                    "temporal_context": None,
                    "geographic_context": "Paris, France",
                    "search_queries": ["Eiffel Tower 330 metres official height"],
                }
            ]
        }
    )
    client = MockGeminiClient(response=SimpleNamespace(parsed=payload, text=None))
    result = GeminiDecompositionService("test-key", "test-model", client).decompose(
        "The Eiffel Tower is 330 metres tall."
    )
    assert len(result.claims) == 1
    assert result.claims[0].text == "The Eiffel Tower is 330 metres tall."


def test_valid_json_text_fallback():
    text = '{"claims":[{"id":"claim-1","text":"Water freezes at zero degrees Celsius.","claim_type":"scientific","entities":["Water"],"search_queries":[]}]}'
    client = MockGeminiClient(response=SimpleNamespace(parsed=None, text=text))
    result = GeminiDecompositionService("test-key", "test-model", client).decompose("Water freezes.")
    assert result.claims[0].claim_type == "scientific"


def test_malformed_json_output():
    client = MockGeminiClient(response=SimpleNamespace(parsed=None, text="not valid json"))
    with pytest.raises(MalformedGeminiOutputError):
        GeminiDecompositionService("test-key", "test-model", client).decompose("Water freezes.")


def test_malformed_pydantic_output():
    client = MockGeminiClient(response=SimpleNamespace(parsed={"claims": [{"id": "x"}]}, text=None))
    with pytest.raises(MalformedGeminiOutputError):
        GeminiDecompositionService("test-key", "test-model", client).decompose("Water freezes.")


def test_provider_error():
    client = MockGeminiClient(error=RuntimeError("provider unavailable"))
    with pytest.raises(GeminiProviderError, match="failed"):
        GeminiDecompositionService("test-key", "test-model", client).decompose("Water freezes.")


def test_single_claim_input():
    payload = {"claims": [{"id": "1", "text": "Tokyo is the capital of Japan.", "claim_type": "geographic", "entities": ["Tokyo", "Japan"], "search_queries": ["Tokyo capital Japan"]}]}
    client = MockGeminiClient(response=SimpleNamespace(parsed=payload, text=None))
    result = GeminiDecompositionService("test-key", "test-model", client).decompose("Tokyo is the capital of Japan.")
    assert len(result.claims) == 1


def test_multiple_claim_input():
    payload = {"claims": [
        {"id": "1", "text": "Tokyo is the capital of Japan.", "claim_type": "geographic", "entities": ["Tokyo", "Japan"], "search_queries": []},
        {"id": "2", "text": "Japan has an emperor.", "claim_type": "political", "entities": ["Japan"], "search_queries": []},
    ]}
    client = MockGeminiClient(response=SimpleNamespace(parsed=payload, text=None))
    result = GeminiDecompositionService("test-key", "test-model", client).decompose("Tokyo is Japan's capital, and Japan has an emperor.")
    assert len(result.claims) == 2


def test_opinion_only_input_returns_no_claims():
    payload = {"claims": []}
    client = MockGeminiClient(response=SimpleNamespace(parsed=payload, text=None))
    result = GeminiDecompositionService("test-key", "test-model", client).decompose("I love chocolate and pizza is the best food.")
    assert result.claims == []


def test_decomposition_schema_accepts_optional_context():
    claim = DecompositionResponse.model_validate(
        {
            "claims": [
                {
                    "id": "claim-1",
                    "text": "The population of Tokyo is about 14 million.",
                    "claim_type": "statistic",
                    "entities": ["Tokyo"],
                    "temporal_context": "about 2024",
                    "geographic_context": "Tokyo, Japan",
                    "search_queries": ["Tokyo population 2024"],
                }
            ]
        }
    ).claims[0]
    assert claim.temporal_context == "about 2024"
    assert claim.geographic_context == "Tokyo, Japan"


def test_gemini_output_schema_rejects_invalid_fields():
    with pytest.raises(ValidationError):
        DecompositionResponse.model_validate(
            {
                "claims": [
                    {"id": "", "text": "short", "claim_type": ""}
                ]
            }
        )
