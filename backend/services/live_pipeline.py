"""Live claim decomposition, search, extraction, retrieval, reranking, and verdict pipeline."""

import logging
import uuid

from backend.core.config import settings
from backend.schemas.claim import AtomicClaim, ClaimSubmission
from backend.schemas.evidence import EvidencePassage
from backend.schemas.investigation import Investigation, InvestigationStatus
from backend.schemas.source import EvidenceChunk, EvidenceSource
from backend.schemas.verdict import Verdict
from backend.services.chunking import chunk_text
from backend.services.gemini_service import GeminiDecompositionService
from backend.services.gemini_verdict import GeminiVerdictService
from backend.services.retrieval import GeminiEmbeddingProvider, hybrid_retrieve
from backend.services.search_providers import SearchProviderError, create_search_provider
from backend.services.source_extractor import SourceExtractor

logger = logging.getLogger(__name__) 


class LivePipelineError(RuntimeError):
    pass


def _deduplicate_results(results: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique: list[dict] = []
    for result in results:
        url = (result.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        unique.append(result)
    return unique


def run_live_pipeline(submission: ClaimSubmission) -> Investigation:
    if not settings.gemini_api_key:
        raise LivePipelineError("GEMINI_API_KEY is not configured.")

    investigation_id = str(uuid.uuid4())
    decomposition = GeminiDecompositionService(
        settings.gemini_api_key, settings.gemini_model
    ).decompose(submission.text)

    atomic_claims: list[AtomicClaim] = []
    for extracted in decomposition.claims:
        atomic_claims.append(AtomicClaim(
            id=extracted.id,
            text=extracted.text,
            source_submission_id=investigation_id,
            claim_type=extracted.claim_type,
            entities=extracted.entities,
            temporal_context=extracted.temporal_context,
            geographic_context=extracted.geographic_context,
            search_queries=extracted.search_queries,
        ))

    try:
        provider = create_search_provider(
            settings.search_provider,
            settings.tavily_api_key,
            settings.extraction_timeout_seconds,
        )
    except SearchProviderError:
        raise

    extractor = SourceExtractor(settings.extraction_timeout_seconds)
    sources: list[EvidenceSource] = []
    chunks: list[EvidenceChunk] = []
    passages: list[EvidencePassage] = []
    verdicts: list[Verdict] = []

    seen_urls: set[str] = set()
    for claim in atomic_claims:
        queries = claim.search_queries or [claim.text]
        search_results: list[dict] = []
        for query in queries[:3]:
            try:
                search_results.extend(provider.search(query, settings.search_result_limit))
            except SearchProviderError as exc:
                logger.warning("Search query failed: %s", exc)

        search_results = _deduplicate_results(search_results)
        claim_sources: list[EvidenceSource] = []
        claim_chunks: list[dict] = []

        for result in search_results:
            url = result["url"]
            if url in seen_urls:
                continue
            seen_urls.add(url)
            source = extractor.extract(url, result.get("title"), result.get("snippet") or "")
            source_id = str(uuid.uuid4())
            source = source.model_copy(update={"id": source_id})
            sources.append(source)
            claim_sources.append(source)

            if not source.text:
                continue

            for text, start, end in chunk_text(source.text, settings.chunk_size, settings.chunk_overlap):
                chunk_id = str(uuid.uuid4())
                chunk_record = {
                    "id": chunk_id,
                    "source_id": source_id,
                    "atomic_claim_id": claim.id,
                    "text": text,
                    "char_start": start,
                    "char_end": end,
                    "lexical_score": None,
                    "semantic_score": None,
                    "fused_score": None,
                    "rerank_score": None,
                }
                claim_chunks.append(chunk_record)

        if not claim_chunks:
            verdicts.append(Verdict(
                atomic_claim_id=claim.id,
                label="INSUFFICIENT_EVIDENCE",
                confidence=0.0,
                explanation="No readable source text was available for this claim.",
                supporting_passage_ids=[],
                refuting_passage_ids=[],
                cited_source_urls=[],
                limitations="Search succeeded or failed without yielding extractable webpage text.",
                is_mock=False,
            ))
            continue

        query_embedding = None
        chunk_embeddings: list[list[float] | None] = []
        embedding_error: str | None = None
        try:
            embedder = GeminiEmbeddingProvider(settings.gemini_api_key, settings.gemini_embedding_model)
            query_embedding = embedder.embed([claim.text])[0]
            chunk_embeddings = [embedding for embedding in embedder.embed([item["text"] for item in claim_chunks])]
        except Exception as exc:
            embedding_error = exc.__class__.__name__
            chunk_embeddings = [None] * len(claim_chunks)

        embedding_chunks = []
        for item, embedding in zip(claim_chunks, chunk_embeddings):
            copied = dict(item)
            if embedding is not None:
                copied["embedding"] = embedding
            embedding_chunks.append(copied)

        if embedding_error:
            for item in embedding_chunks:
                item["query_embedding"] = None
                item["embeddings"] = None
        else:
            embeddings = [item.pop("embedding", None) for item in embedding_chunks]
            for item in embedding_chunks:
                item["query_embedding"] = query_embedding
                item["embeddings"] = embeddings

        ranked = hybrid_retrieve(claim.text, embedding_chunks, settings.retrieval_chunk_limit)

        # Optional cross-encoder reranking; otherwise fused hybrid rank is the documented fallback.
        if settings.reranker_enabled:
            try:
                import importlib

                module = importlib.import_module("sentence_transformers")
                cross_encoder = getattr(module, "CrossEncoder")
                model = cross_encoder(settings.reranker_model)
                pairs = [(claim.text, item["text"]) for item in ranked]
                rerank_scores = model.predict(pairs)
                for item, score in zip(ranked, rerank_scores):
                    item["rerank_score"] = float(score)
                ranked.sort(key=lambda item: item["rerank_score"], reverse=True)
            except Exception as exc:
                logger.warning("Cross-encoder reranker unavailable; using hybrid fallback: %s", exc.__class__.__name__) 

        for item in ranked:
            chunks.append(EvidenceChunk(
                id=item["id"],
                source_id=item["source_id"],
                atomic_claim_id=claim.id,
                text=item["text"],
                char_start=item["char_start"],
                char_end=item["char_end"],
                lexical_score=item.get("lexical_score"),
                semantic_score=item.get("semantic_score"),
                fused_score=item.get("fused_score"),
                rerank_score=item.get("rerank_score"),
            ))

        passage_payload: list[dict] = []
        for item in ranked:
            source = next((s for s in claim_sources if s.id == item["source_id"]), None)
            passage_id = str(uuid.uuid4())
            passage = EvidencePassage(
                id=passage_id,
                atomic_claim_id=claim.id,
                chunk_id=item["id"],
                text=item["text"],
                source_url=source.url if source else None,
                source_title=source.title if source else None,
                relevance_score=max(0.0, min(1.0, item.get("fused_score") or 0.0)),
                rerank_score=item.get("rerank_score"),
                is_mock=False,
            )
            passages.append(passage)
            passage_payload.append({
                "id": passage.id,
                "source_url": passage.source_url,
                "text": passage.text,
            })

        verdict_result = GeminiVerdictService(
            settings.gemini_api_key, settings.gemini_model
        ).assess(claim.text, passage_payload)
        verdicts.append(Verdict(
            atomic_claim_id=claim.id,
            label=verdict_result.label,
            confidence=verdict_result.confidence,
            explanation=verdict_result.explanation,
            supporting_passage_ids=verdict_result.supporting_passage_ids,
            refuting_passage_ids=verdict_result.refuting_passage_ids,
            cited_source_urls=verdict_result.cited_source_urls,
            limitations=(
                verdict_result.limitations
                + (" Embedding retrieval was unavailable; BM25/hybrid fallback was used." if embedding_error else "")
            ) if verdict_result.limitations or embedding_error else None,
            is_mock=False,
        ))

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
