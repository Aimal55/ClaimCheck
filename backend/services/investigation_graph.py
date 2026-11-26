"""LangGraph implementation of the live ClaimCheck investigation pipeline."""

import logging
import uuid
from typing import Literal, TypedDict

from langgraph.graph import END, StateGraph

from backend.core.config import settings
from backend.schemas.claim import AtomicClaim, ClaimSubmission
from backend.schemas.evidence import EvidencePassage
from backend.schemas.investigation import Investigation, InvestigationStatus
from backend.schemas.source import EvidenceChunk, EvidenceSource
from backend.schemas.verdict import Verdict
from backend.services.langchain_chunking import split_source_documents
from backend.services.langchain_gemini import LangChainGeminiService
from backend.services.gemini_service import MissingGeminiAPIKeyError
from backend.services.retrieval import GeminiEmbeddingProvider, hybrid_retrieve
from backend.services.search_providers import SearchProviderError, create_search_provider
from backend.services.source_extractor import SourceExtractor

logger = logging.getLogger(__name__)


class InvestigationGraphState(TypedDict, total=False):
    submission_text: str
    investigation_id: str
    atomic_claims: list[dict]
    search_results: list[dict]
    sources: list[dict]
    chunks: list[dict]
    passages: list[dict]
    verdicts: list[dict]
    retry_count: int
    weak_claims: list[str]
    error: str | None
    retry_search_used: bool
    quality_retry_pending: bool


def decompose_claims(state: InvestigationGraphState) -> InvestigationGraphState:
    if not settings.gemini_api_key:
        return {**state, "error": "GEMINI_API_KEY is not configured."}

    try:
        result = LangChainGeminiService(
            settings.gemini_api_key, settings.gemini_model
        ).decompose(state["submission_text"])
        claims = []
        for extracted in result.claims:
            claims.append({
                "id": extracted.id,
                "text": extracted.text,
                "source_submission_id": state["investigation_id"],
                "claim_type": extracted.claim_type,
                "entities": extracted.entities,
                "temporal_context": extracted.temporal_context,
                "geographic_context": extracted.geographic_context,
                "search_queries": extracted.search_queries,
            })
        return {**state, "atomic_claims": claims}
    except Exception as exc:
        logger.exception("Claim decomposition failed")
        return {**state, "error": f"Claim decomposition failed: {exc.__class__.__name__}"}


def search_sources(state: InvestigationGraphState) -> InvestigationGraphState:
    if state.get("error"):
        return state
    try:
        provider = create_search_provider(
            settings.search_provider,
            settings.tavily_api_key,
            settings.extraction_timeout_seconds,
        )
    except SearchProviderError as exc:
        return {**state, "error": str(exc)}

    seen: set[str] = set()
    results: list[dict] = []
    extra_attempt = state.get("retry_count", 0) > 0
    for claim in state.get("atomic_claims", []):
        queries = claim.get("search_queries") or [claim["text"]]
        if extra_attempt:
            queries = queries[:1] + [f"independent evidence {claim['text']}"]
        for query in queries[:3]:
            try:
                for result in provider.search(query, settings.search_result_limit):
                    url = (result.get("url") or "").strip()
                    if url and url not in seen:
                        seen.add(url)
                        results.append({**result, "atomic_claim_id": claim["id"]})
            except SearchProviderError as exc:
                logger.warning("Search failed for %s: %s", query, exc)
    return {**state, "search_results": results}


def extract_and_chunk(state: InvestigationGraphState) -> InvestigationGraphState:
    if state.get("error"):
        return state

    extractor = SourceExtractor(settings.extraction_timeout_seconds)
    sources: list[dict] = list(state.get("sources", []))
    chunks: list[dict] = list(state.get("chunks", []))
    seen_sources = {source["url"] for source in sources}

    for result in state.get("search_results", []):
        url = result["url"]
        if url in seen_sources:
            continue
        seen_sources.add(url)
        extracted = extractor.extract(url, result.get("title"), result.get("snippet") or "")
        source_id = str(uuid.uuid4())
        source = extracted.model_copy(update={"id": source_id})
        sources.append(source.model_dump(mode="python"))
        if not source.text:
            continue

        records = split_source_documents(
            source_id=source_id,
            atomic_claim_id=result["atomic_claim_id"],
            text=source.text,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
        chunks.extend(records)

    return {
        **state,
        "sources": sources,
        "chunks": chunks,
    }


def retrieve_evidence(state: InvestigationGraphState) -> InvestigationGraphState:
    if state.get("error"):
        return state

    passages: list[dict] = []
    for claim in state.get("atomic_claims", []):
        claim_chunks = [
            chunk for chunk in state.get("chunks", [])
            if chunk["atomic_claim_id"] == claim["id"]
        ]
        if not claim_chunks:
            continue

        try:
            embedder = GeminiEmbeddingProvider(settings.gemini_api_key, settings.gemini_embedding_model)
            query_embedding = embedder.embed([claim["text"]])[0]
            embeddings = embedder.embed([chunk["text"] for chunk in claim_chunks])
        except Exception as exc:
            logger.warning("Embedding retrieval unavailable: %s", exc.__class__.__name__)
            query_embedding = None
            embeddings = [None] * len(claim_chunks)

        for chunk, embedding in zip(claim_chunks, embeddings):
            chunk["query_embedding"] = query_embedding
            chunk["embeddings"] = embeddings

        ranked = hybrid_retrieve(claim["text"], claim_chunks, settings.retrieval_chunk_limit)
        sources_by_id = {source["id"]: source for source in state.get("sources", [])}
        for item in ranked:
            source = sources_by_id.get(item["source_id"])
            passage_id = str(uuid.uuid4())
            passages.append({
                "id": passage_id,
                "atomic_claim_id": claim["id"],
                "chunk_id": item["id"],
                "text": item["text"],
                "source_url": source["url"] if source else None,
                "source_title": source.get("title") if source else None,
                "relevance_score": max(0.0, min(1.0, item.get("fused_score") or 0.0)),
                "rerank_score": item.get("rerank_score"),
                "stance": None,
                "is_mock": False,
            })
    return {**state, "passages": passages}


def rerank_evidence(state: InvestigationGraphState) -> InvestigationGraphState:
    if state.get("error") or not state.get("passages"):
        return state

    passages = state["passages"]
    if not settings.reranker_enabled:
        return state

    try:
        import importlib
        module = importlib.import_module("sentence_transformers")
        cross_encoder = getattr(module, "CrossEncoder")
        reranker = cross_encoder(settings.reranker_model)
        for claim in state.get("atomic_claims", []):
            claim_passages = [p for p in passages if p["atomic_claim_id"] == claim["id"]]
            scores = reranker.predict([(claim["text"], p["text"]) for p in claim_passages])
            for passage, score in zip(claim_passages, scores):
                passage["rerank_score"] = float(score)
            claim_passages.sort(key=lambda p: p.get("rerank_score") or 0.0, reverse=True)
    except Exception as exc:
        logger.warning("Cross-encoder unavailable; hybrid ranking retained: %s", exc.__class__.__name__)
    return state


def verify_claims(state: InvestigationGraphState) -> InvestigationGraphState:
    if state.get("error"):
        return state

    service = LangChainGeminiService(settings.gemini_api_key, settings.gemini_model)
    verdicts: list[dict] = []
    weak_claim_ids: list[str] = []

    for claim in state.get("atomic_claims", []):
        claim_passages = [p for p in state.get("passages", []) if p["atomic_claim_id"] == claim["id"]]
        try:
            result = service.assess(claim["text"], claim_passages)
        except Exception as exc:
            logger.exception("Gemini verdict failed")
            return {**state, "error": f"Evidence verdict failed: {exc.__class__.__name__}"}

        verdict = {
            "atomic_claim_id": claim["id"],
            "label": result.label,
            "confidence": result.confidence,
            "explanation": result.explanation,
            "supporting_passage_ids": result.supporting_passage_ids,
            "refuting_passage_ids": result.refuting_passage_ids,
            "cited_source_urls": result.cited_source_urls,
            "limitations": result.limitations,
            "is_mock": False,
        }
        verdicts.append(verdict)
        if result.label == "INSUFFICIENT_EVIDENCE" or result.confidence < 0.5:
            weak_claim_ids.append(claim["id"])

    return {**state, "verdicts": verdicts, "weak_claims": weak_claim_ids}


def check_evidence_quality(state: InvestigationGraphState) -> InvestigationGraphState:
    if state.get("weak_claims") and state.get("retry_count", 0) == 0:
        return {**state, "retry_count": 1, "quality_retry_pending": True}
    if state.get("quality_retry_pending"):
        return {**state, "quality_retry_pending": False}
    return state


def quality_route(state: InvestigationGraphState) -> Literal["search_sources", "finalize_investigation"]:
    if state.get("quality_retry_pending"):
        return "search_sources"
    if state.get("weak_claims") and state.get("retry_count", 0) == 0:
        return "search_sources"
    return "finalize_investigation"


def finalize_investigation(state: InvestigationGraphState) -> InvestigationGraphState:
    return state


def build_investigation_graph():
    builder = StateGraph(InvestigationGraphState)
    builder.add_node("decompose_claims", decompose_claims)
    builder.add_node("search_sources", search_sources)
    builder.add_node("extract_and_chunk", extract_and_chunk)
    builder.add_node("retrieve_evidence", retrieve_evidence)
    builder.add_node("rerank_evidence", rerank_evidence)
    builder.add_node("verify_claims", verify_claims)
    builder.add_node("check_evidence_quality", check_evidence_quality)
    builder.add_node("finalize_investigation", finalize_investigation)

    builder.set_entry_point("decompose_claims")
    builder.add_edge("decompose_claims", "search_sources")
    builder.add_edge("search_sources", "extract_and_chunk")
    builder.add_edge("extract_and_chunk", "retrieve_evidence")
    builder.add_edge("retrieve_evidence", "rerank_evidence")
    builder.add_edge("rerank_evidence", "verify_claims")
    builder.add_edge("verify_claims", "check_evidence_quality")
    builder.add_conditional_edges(
        "check_evidence_quality",
        quality_route,
        {"search_sources": "search_sources", "finalize_investigation": "finalize_investigation"},
    )
    builder.add_edge("finalize_investigation", END)
    return builder.compile()


INVESTIGATION_GRAPH = build_investigation_graph()


def run_langgraph_pipeline(submission: ClaimSubmission) -> Investigation:
    if not settings.gemini_api_key:
        raise MissingGeminiAPIKeyError("GEMINI_API_KEY is not configured.")

    investigation_id = str(uuid.uuid4())
    initial: InvestigationGraphState = {
        "submission_text": submission.text,
        "investigation_id": investigation_id,
        "atomic_claims": [],
        "search_results": [],
        "sources": [],
        "chunks": [],
        "passages": [],
        "verdicts": [],
        "retry_count": 0,
        "weak_claims": [],
        "error": None,
        "retry_search_used": False,
        "quality_retry_pending": False,
    }
    state = INVESTIGATION_GRAPH.invoke(initial)
    if state.get("error"):
        raise RuntimeError(state["error"])

    atomic_claims = [AtomicClaim.model_validate(claim) for claim in state.get("atomic_claims", [])]
    sources = [EvidenceSource.model_validate(source) for source in state.get("sources", [])]
    chunks = []
    for chunk in state.get("chunks", []):
        chunk_data = {key: value for key, value in chunk.items() if key not in {"document", "query_embedding", "embeddings"}}
        chunks.append(EvidenceChunk.model_validate(chunk_data))

    passages = [EvidencePassage.model_validate(passage) for passage in state.get("passages", [])]
    verdicts = [Verdict.model_validate(verdict) for verdict in state.get("verdicts", [])]

    return Investigation(
        id=investigation_id,
        submission=submission,
        atomic_claims=atomic_claims,
        evidence_passages=passages,
        verdicts=verdicts,
        sources=sources,
        chunks=chunks,
        status=InvestigationStatus.COMPLETE,
        is_mock=False,
        mock_disclaimer=None,
    )
