"""
Investigation — the top-level response object.

An Investigation ties together:
  - the original ClaimSubmission
  - the decomposed AtomicClaims
  - the retrieved EvidencePassages
  - the Verdicts for each claim
  - metadata (status, timestamps, mock flag)
"""

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from backend.schemas.claim import AtomicClaim, ClaimSubmission
from backend.schemas.evidence import EvidencePassage
from backend.schemas.verdict import Verdict
from backend.schemas.source import EvidenceChunk, EvidenceSource


class InvestigationStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETE = "COMPLETE"
    ERROR = "ERROR"


class Investigation(BaseModel):
    """
    Full result of a claim-verification run.

    This is what the API returns and what gets stored in SQLite (as JSON).
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(..., description="Unique investigation ID (UUID4).")
    submission: ClaimSubmission
    atomic_claims: list[AtomicClaim] = Field(default_factory=list)
    evidence_passages: list[EvidencePassage] = Field(default_factory=list)
    verdicts: list[Verdict] = Field(default_factory=list)
    status: InvestigationStatus = InvestigationStatus.PENDING
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when this investigation was created.",
    )
    is_mock: bool = Field(
        default=False,
        description=(
            "True when results were produced by the mock pipeline. "
            "DO NOT present mock results as real fact-checks."
        ),
    )
    mock_disclaimer: str | None = Field(
        default=None,
        description="Shown in the UI whenever is_mock=True.",
    )
    sources: list[EvidenceSource] = Field(default_factory=list)
    chunks: list[EvidenceChunk] = Field(default_factory=list)
