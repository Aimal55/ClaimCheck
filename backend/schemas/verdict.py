"""
Verdict schemas.

VerdictLabel — controlled vocabulary of possible outcomes.
Verdict       — the final decision for one AtomicClaim, plus explanation.
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class VerdictLabel(str, Enum):
    """
    Possible fact-check outcomes.

    Using str mixin so values serialize to plain JSON strings without
    extra configuration (e.g. "SUPPORTED", not 1 or {"value": "SUPPORTED"}).
    """

    SUPPORTED = "SUPPORTED"
    REFUTED = "REFUTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    UNVERIFIED = "UNVERIFIED"  # default for mock / not-yet-processed


class Verdict(BaseModel):
    """The fact-check decision for a single AtomicClaim."""

    model_config = ConfigDict(frozen=True)

    atomic_claim_id: str = Field(
        ..., description="The AtomicClaim this verdict applies to."
    )
    label: VerdictLabel = Field(..., description="Fact-check outcome label.")
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Model confidence in this verdict (0–1). None when not computed.",
    )
    explanation: str = Field(
        ...,
        description="Plain-language explanation of how the verdict was reached.",
    )
    supporting_passage_ids: list[str] = Field(default_factory=list)
    refuting_passage_ids: list[str] = Field(default_factory=list)
    cited_source_urls: list[str] = Field(default_factory=list)
    limitations: str | None = None
    is_mock: bool = Field(
        default=False,
        description="True when this verdict was produced by the mock pipeline.",
    )
