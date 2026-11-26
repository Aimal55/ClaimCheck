"""LangChain wrappers for Gemini decomposition and verdict generation."""

from langchain_google_genai import ChatGoogleGenerativeAI

from backend.services.gemini_service import DecompositionResponse
from backend.services.gemini_verdict import AtomicVerdictResult


class LangChainGeminiService:
    def __init__(self, api_key: str, model: str) -> None:
        self.chat = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=api_key,
            temperature=0.0,
            request_timeout=60,
            retries=2,
        )

    def decompose(self, text: str) -> DecompositionResponse:
        structured = self.chat.with_structured_output(DecompositionResponse)
        prompt = (
            "Extract independently verifiable factual claims only. Do not invent facts. "
            "Preserve names, dates, numbers, units, and meaning. Return no claims for opinions. "
            f"Input: {text}"
        )
        result = structured.invoke(prompt)
        if isinstance(result, DecompositionResponse):
            return result
        return DecompositionResponse.model_validate(result)

    def assess(self, claim: str, passages: list[dict]) -> AtomicVerdictResult:
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

        evidence = "\n\n".join(
            f"PASSAGE_ID={p['id']} SOURCE_URL={p['source_url']}\n{p['text']}"
            for p in passages
        )
        structured = self.chat.with_structured_output(AtomicVerdictResult)
        prompt = (
            "Assess the claim only against supplied evidence. Never invent passage IDs or URLs. "
            "Choose SUPPORTED, REFUTED, CONFLICTING_EVIDENCE, or INSUFFICIENT_EVIDENCE.\n"
            f"CLAIM: {claim}\n\nEVIDENCE:\n{evidence}"
        )
        result = structured.invoke(prompt)
        if isinstance(result, AtomicVerdictResult):
            verdict = result
        else:
            verdict = AtomicVerdictResult.model_validate(result)

        valid_ids = {p["id"] for p in passages}
        valid_urls = {p["source_url"] for p in passages}
        return verdict.model_copy(update={
            "supporting_passage_ids": [p for p in verdict.supporting_passage_ids if p in valid_ids],
            "refuting_passage_ids": [p for p in verdict.refuting_passage_ids if p in valid_ids],
            "cited_source_urls": [u for u in verdict.cited_source_urls if u in valid_urls],
        })
