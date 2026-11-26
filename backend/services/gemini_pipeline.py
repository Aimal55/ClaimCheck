"""Gemini atomic-decomposition pipeline without mock evidence or verdicts."""

import logging
import uuid

from backend.core.config import settings
from backend.schemas.claim import AtomicClaim, ClaimSubmission
from backend.schemas.investigation import Investigation, InvestigationStatus
from backend.schemas.verdict import Verdict, VerdictLabel
from backend.services.gemini_service import GeminiDecompositionService

logger = logging.getLogger(__name__)


def run_gemini_decomposition_pipeline(submission: ClaimSubmission) -> Investigation:
    """Decompose a submission with Gemini and leave verification evidence empty."""
    investigation_id = str(uuid.uuid4())
    service = GeminiDecompositionService(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
    )

    try:
        result = service.decompose(submission.text)
    except Exception:
        raise

    atomic_claims: list[AtomicClaim] = []
    verdicts: list[Verdict] = []

    for extracted in result.claims:
        claim_id = extracted.id
        atomic_claims.append(
            AtomicClaim(
                id=claim_id,
                text=extracted.text,
                source_submission_id=investigation_id,
                claim_type=extracted.claim_type,
                entities=extracted.entities,
                temporal_context=extracted.temporal_context,
                geographic_context=extracted.geographic_context,
                search_queries=extracted.search_queries,
            )
        )
        verdicts.append(
            Verdict(
                atomic_claim_id=claim_id,
                label=VerdictLabel.UNVERIFIED,
                confidence=None,
                explanation=(
                    "No evidence retrieval or real verdict generation was performed in Phase 1."
                ),
                is_mock=False,
            )
        )

    logger.info("Gemini decomposed submission into %d atomic claim(s)", len(atomic_claims))

    return Investigation(
        id=investigation_id,
        submission=submission,
        atomic_claims=atomic_claims,
        evidence_passages=[],
        verdicts=verdicts,
        status=InvestigationStatus.COMPLETE,
        is_mock=False,
        mock_disclaimer=None,
    )