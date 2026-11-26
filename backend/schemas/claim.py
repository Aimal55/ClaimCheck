"""
Claim schemas.

ClaimSubmission  — what the client POSTs.
AtomicClaim      — a single verifiable statement decomposed from the submission.

Keeping them separate because one submitted claim may eventually be broken into
multiple atomic claims by the decomposition service (not built yet in milestone 1).
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ClaimSubmission(BaseModel):
    """Raw claim text submitted by the user."""

    model_config = ConfigDict(str_strip_whitespace=True)

    text: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="The factual claim to investigate.",
        examples=["The Eiffel Tower is located in Berlin."],
    )

    @field_validator("text")
    @classmethod
    def no_blank_text(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Claim text must not be blank or whitespace only.")
        return v


class AtomicClaim(BaseModel):
    """
    A single, independently verifiable statement.

    In milestone 1 the submitted text is used as-is as the sole atomic claim.
    Future milestones will add a decomposition step that may produce multiple
    AtomicClaims from one ClaimSubmission.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(..., description="Unique identifier for this atomic claim.")
    text: str = Field(..., description="The verifiable statement.")
    source_submission_id: str = Field(
        ..., description="ID of the parent ClaimSubmission."
    )
    claim_type: str | None = Field(
        default=None,
        description="Type of factual claim extracted by the provider.",
    )
    entities: list[str] = Field(
        default_factory=list,
        description="Names or entities preserved from the submitted claim.",
    )
    temporal_context: str | None = Field(
        default=None,
        description="Optional date, period, or time qualifier.",
    )
    geographic_context: str | None = Field(
        default=None,
        description="Optional place or geographic scope.",
    )
    search_queries: list[str] = Field(
        default_factory=list,
        description="Search queries proposed by the decomposition provider.",
    )
