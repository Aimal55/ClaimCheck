"""Evidence-based Gemini verdict generation with Pydantic validation."""

from pydantic import BaseModel, ConfigDict, Field
from google import genai
from google.genai import types


class AtomicVerdictResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    explanation: str
    supporting_passage_ids: list[str] = Field(default_factory=list)
    refuting_passage_ids: list[str] = Field(default_factory=list)
    cited_source_urls: list[str] = Field(default_factory=list)
    limitations: str | None = None


class GeminiVerdictService:
    def __init__(self, api_key: str, model: str) -> None:
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def assess(self, claim: str, passages: list[dict]) -> AtomicVerdictResult:
        allowed = {"SUPPORTED", "REFUTED", "CONFLICTING_EVIDENCE", "INSUFFICIENT_EVIDENCE"}
        if not passages:
            return AtomicVerdictResult(
                label="INSUFFICIENT_EVIDENCE",
                confidence=0.0,
                explanation="No readable retrieved evidence was available.",
                supporting_passage_ids=[],
                refuting_passage_ids=[],
                cited_source_urls=[],
                limitations="No source text could be extracted.",
            )

        evidence_text = "\n\n".join(
            f"PASSAGE_ID={p['id']} SOURCE_URL={p['source_url']}\n{p['text']}"
            for p in passages
        )
        prompt = (
            "Assess the factual claim only against the supplied evidence passages.\n"
            "Never invent sources or passage IDs. Use only cited passage IDs and URLs shown below.\n"
            "Use SUPPORTED, REFUTED, CONFLICTING_EVIDENCE, or INSUFFICIENT_EVIDENCE.\n"
            "Use INSUFFICIENT_EVIDENCE for weak, missing, or unrelated evidence.\n"
            f"CLAIM: {claim}\n\nEVIDENCE:\n{evidence_text}"
        )
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=AtomicVerdictResult,
            ),
        )
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, dict):
            result = AtomicVerdictResult.model_validate(parsed)
        elif isinstance(parsed, AtomicVerdictResult):
            result = parsed
        else:
            import json
            result = AtomicVerdictResult.model_validate_json(getattr(response, "text", "{}"))

        if result.label not in allowed:
            raise ValueError("Gemini returned an invalid verdict label")

        valid_ids = {p["id"] for p in passages}
        valid_urls = {p["source_url"] for p in passages}
        return result.model_copy(update={
            "supporting_passage_ids": [pid for pid in result.supporting_passage_ids if pid in valid_ids],
            "refuting_passage_ids": [pid for pid in result.refuting_passage_ids if pid in valid_ids],
            "cited_source_urls": [url for url in result.cited_source_urls if url in valid_urls],
        })
