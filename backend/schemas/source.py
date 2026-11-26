"""Evidence source and text chunk schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EvidenceSource(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str | None = None
    url: str
    title: str | None = None
    text: str | None = None
    publication_date: str | None = None
    retrieved_at: datetime
    extraction_status: str
    extraction_error: str | None = None
    search_snippet: str | None = None


class EvidenceChunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    source_id: str
    atomic_claim_id: str
    text: str = Field(..., min_length=1)
    char_start: int = Field(..., ge=0)
    char_end: int = Field(..., ge=0)
    lexical_score: float | None = None
    semantic_score: float | None = None
    fused_score: float | None = None
    rerank_score: float | None = None
