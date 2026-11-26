"""Hybrid BM25 + Gemini embedding retrieval with reciprocal rank fusion."""

import math
import re
from typing import Iterable

import numpy as np
from google import genai
from rank_bm25 import BM25Okapi


_TOKEN_PATTERN = re.compile(r"[^\w]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return [part for part in _TOKEN_PATTERN.sub(" ", text.lower()).split() if part]


def reciprocal_rank_fusion(rankings: Iterable[list[str]], k: int = 60) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return scores


class GeminiEmbeddingProvider:
    def __init__(self, api_key: str, model: str) -> None:
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self.client.models.embed_content(
            model=self.model,
            contents=texts,
        )
        embeddings = getattr(response, "embeddings", None)
        if not embeddings:
            raise RuntimeError("Gemini embedding provider returned no embeddings.")
        return [list(item.values) for item in embeddings]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(
        sum(value * value for value in right)
    )
    if denominator == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / denominator


def hybrid_retrieve(query: str, chunks: list[dict], limit: int = 12) -> list[dict]:
    """Fuse BM25 and optional semantic rankings using reciprocal rank fusion."""
    if not chunks:
        return []

    corpus = [tokenize(chunk["text"]) for chunk in chunks]
    bm25 = BM25Okapi(corpus) if corpus and all(corpus) else None
    lexical_order: list[str] = []
    if bm25:
        scores = bm25.get_scores(tokenize(query))
        lexical_order = [
            chunks[index]["id"]
            for index in sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
        ]

    semantic_order: list[str] = []
    embeddings = chunks[0].get("embeddings")
    query_embedding = chunks[0].get("query_embedding")
    if embeddings is not None and query_embedding is not None:
        scored = sorted(
            (
                (chunk["id"], cosine_similarity(query_embedding, chunk_embedding))
                for chunk, chunk_embedding in zip(chunks, embeddings)
                if chunk_embedding
            ),
            key=lambda pair: pair[1],
            reverse=True,
        )
        semantic_order = [item_id for item_id, _ in scored]

    fused = reciprocal_rank_fusion(
        [ranking for ranking in (lexical_order, semantic_order) if ranking]
    )
    for chunk in chunks:
        chunk["fused_score"] = fused.get(chunk["id"], 0.0)

    return sorted(chunks, key=lambda chunk: chunk["fused_score"], reverse=True)[:limit]
