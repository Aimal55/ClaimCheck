"""Gemini-backed atomic claim decomposition service."""

import json
import logging
from typing import Any, Protocol

from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__) 


class MissingGeminiAPIKeyError(RuntimeError):
    """Raised when Gemini credentials are not configured."""


class GeminiProviderError(RuntimeError):
    """Raised when Gemini cannot complete a provider request."""


class MalformedGeminiOutputError(ValueError):
    """Raised when Gemini returns JSON that does not match the required schema."""


class AtomicClaimDecomposition(BaseModel):
    """One independently verifiable claim extracted from a submission."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(..., min_length=1)
    text: str = Field(..., min_length=10, max_length=2000)
    claim_type: str = Field(..., min_length=1)
    entities: list[str] = Field(default_factory=list)
    temporal_context: str | None = None
    geographic_context: str | None = None
    search_queries: list[str] = Field(default_factory=list)


class DecompositionResponse(BaseModel):
    """Structured Gemini response for claim decomposition."""

    claims: list[AtomicClaimDecomposition] = Field(default_factory=list)


class GeminiClientProtocol(Protocol):
    @property
    def models(self) -> Any: ...


class GeminiDecompositionService:
    """Testable service that extracts atomic factual claims using Gemini."""

    def __init__(
        self,
        api_key: str,
        model: str,
        client: GeminiClientProtocol | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise MissingGeminiAPIKeyError("GEMINI_API_KEY is not configured.")
        if not model or not model.strip():
            raise GeminiProviderError("GEMINI_MODEL is not configured.")

        self.api_key = api_key
        self.model = model
        self.client = client or genai.Client(api_key=api_key)

    def decompose(self, text: str) -> DecompositionResponse:
        prompt = (
            "Extract only independently verifiable factual claims from the input.\n"
            "Do not invent facts, opinions, questions, recommendations, or sources.\n"
            "Preserve names, dates, numbers, units, and original meaning exactly.\n"
            "Do not turn opinions or subjective statements into factual claims.\n"
            "For each factual claim, return a stable ID and a concise factual text.\n"
            "Assign a claim_type, relevant entities, optional temporal/geographic context, "
            "and 1-3 useful web search queries.\n"
            "If the input contains only opinions or no verifiable factual claims, return {\"claims\": []}.\n"
            f"Input claim: {text}"
        )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=DecompositionResponse,
                ),
            )
        except Exception as exc:
            logger.error("Gemini decomposition provider call failed")
            raise GeminiProviderError("Gemini claim decomposition failed.") from exc

        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            if isinstance(parsed, DecompositionResponse):
                return parsed
            if isinstance(parsed, dict):
                try:
                    return DecompositionResponse.model_validate(parsed)
                except ValidationError as exc:
                    raise MalformedGeminiOutputError(
                        "Gemini returned malformed structured claim data."
                    ) from exc

        response_text = getattr(response, "text", None)
        if not response_text:
            raise MalformedGeminiOutputError("Gemini returned no JSON output.")

        try:
            payload = json.loads(response_text)
            return DecompositionResponse.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise MalformedGeminiOutputError(
                "Gemini returned malformed structured claim data."
            ) from exc
