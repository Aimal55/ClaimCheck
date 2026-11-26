"""
Schema unit tests.

These tests exercise Pydantic validation logic in isolation —
no database, no HTTP, no network required.
"""

import pytest
from pydantic import ValidationError

from backend.schemas.claim import AtomicClaim, ClaimSubmission
from backend.schemas.evidence import EvidencePassage
from backend.schemas.investigation import Investigation, InvestigationStatus
from backend.schemas.verdict import Verdict, VerdictLabel


# ---------------------------------------------------------------------------
# ClaimSubmission
# ---------------------------------------------------------------------------

class TestClaimSubmission:
    def test_valid_claim(self):
        sub = ClaimSubmission(text="The sky is blue on a clear day.")
        assert sub.text == "The sky is blue on a clear day."

    def test_whitespace_stripped(self):
        sub = ClaimSubmission(text="  Gravity pulls objects downward.  ")
        assert sub.text == "Gravity pulls objects downward."

    def test_too_short_raises(self):
        with pytest.raises(ValidationError, match="at least 10"):
            ClaimSubmission(text="Short")

    def test_blank_raises(self):
        with pytest.raises(ValidationError):
            ClaimSubmission(text="          ")  # whitespace-only after strip

    def test_too_long_raises(self):
        with pytest.raises(ValidationError):
            ClaimSubmission(text="x" * 2001)

    def test_exactly_min_length(self):
        ClaimSubmission(text="1234567890")  # 10 chars — should pass

    def test_exactly_max_length(self):
        ClaimSubmission(text="x" * 2000)  # should pass


# ---------------------------------------------------------------------------
# AtomicClaim
# ---------------------------------------------------------------------------

class TestAtomicClaim:
    def test_valid(self):
        claim = AtomicClaim(
            id="abc",
            text="Water boils at 100°C at sea level.",
            source_submission_id="inv-1",
        )
        assert claim.id == "abc"

    def test_immutable(self):
        claim = AtomicClaim(id="a", text="x" * 10, source_submission_id="s")
        with pytest.raises(Exception):  # frozen model
            claim.id = "b"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# EvidencePassage
# ---------------------------------------------------------------------------

class TestEvidencePassage:
    def test_valid_minimal(self):
        passage = EvidencePassage(
            id="p1", atomic_claim_id="c1", text="Some evidence text."
        )
        assert passage.source_url is None
        assert passage.is_mock is False

    def test_relevance_out_of_range_raises(self):
        with pytest.raises(ValidationError):
            EvidencePassage(
                id="p1", atomic_claim_id="c1", text="text", relevance_score=1.5
            )

    def test_negative_relevance_raises(self):
        with pytest.raises(ValidationError):
            EvidencePassage(
                id="p1", atomic_claim_id="c1", text="text", relevance_score=-0.1
            )


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------

class TestVerdict:
    def test_valid_verdict(self):
        v = Verdict(
            atomic_claim_id="c1",
            label=VerdictLabel.SUPPORTED,
            explanation="Strong evidence found.",
        )
        assert v.label == VerdictLabel.SUPPORTED
        assert v.label == "SUPPORTED"  # str mixin

    def test_unverified_default_label(self):
        v = Verdict(
            atomic_claim_id="c1",
            label=VerdictLabel.UNVERIFIED,
            explanation="No analysis performed.",
            is_mock=True,
        )
        assert v.is_mock is True

    def test_confidence_out_of_range_raises(self):
        with pytest.raises(ValidationError):
            Verdict(
                atomic_claim_id="c1",
                label=VerdictLabel.SUPPORTED,
                explanation="x",
                confidence=1.1,
            )

    def test_verdict_label_values(self):
        labels = {v.value for v in VerdictLabel}
        assert "SUPPORTED" in labels
        assert "REFUTED" in labels
        assert "UNVERIFIED" in labels


# ---------------------------------------------------------------------------
# Investigation
# ---------------------------------------------------------------------------

class TestInvestigation:
    def test_defaults(self):
        inv = Investigation(
            id="inv-1",
            submission=ClaimSubmission(text="A verifiable factual statement."),
        )
        assert inv.status == InvestigationStatus.PENDING
        assert inv.atomic_claims == []
        assert inv.is_mock is False
        assert inv.created_at is not None

    def test_mock_flag_propagates(self):
        inv = Investigation(
            id="inv-2",
            submission=ClaimSubmission(text="Another verifiable factual statement."),
            is_mock=True,
            mock_disclaimer="This is mock data.",
        )
        assert inv.is_mock is True
        assert inv.mock_disclaimer == "This is mock data."
