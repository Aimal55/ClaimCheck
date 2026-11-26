"""
Investigations router.

Endpoints
---------
POST /api/v1/investigations
    Submit a claim, run the pipeline, persist the investigation, return it.

GET  /api/v1/investigations/{investigation_id}
    Retrieve a previously-saved investigation by ID.

GET  /api/v1/investigations
    List recent investigation summaries (id, status, created_at).
"""

import logging

from fastapi import APIRouter, HTTPException, Query, status

from backend.db.database import get_investigation, list_investigations, save_investigation
from backend.schemas.claim import ClaimSubmission
from backend.schemas.investigation import Investigation
from backend.services.mock_pipeline import run_mock_pipeline
from backend.services.search_providers import SearchProviderError
from backend.services.investigation_graph import run_langgraph_pipeline
from backend.services.gemini_service import (
    GeminiProviderError,
    MalformedGeminiOutputError,
    MissingGeminiAPIKeyError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/investigations", tags=["investigations"])


@router.post(
    "",
    response_model=Investigation,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a claim for investigation",
)
def create_investigation(
    submission: ClaimSubmission, use_mock: bool = Query(True)
) -> Investigation:
    """
    Validate the submitted claim, run it through the pipeline
    (mock in milestone 1), save the result, and return it.

    Raises 422 automatically if the claim fails Pydantic validation.
    """
    logger.info("Received claim submission: %.80s…", submission.text)

    try:
        if use_mock:
            investigation = run_mock_pipeline(submission)
        else:
            investigation = run_langgraph_pipeline(submission)
    except MissingGeminiAPIKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except MalformedGeminiOutputError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except GeminiProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except SearchProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Pipeline error for submission: %s", submission.text)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Investigation pipeline failed. Please try again.",
        ) from exc

    try:
        save_investigation(investigation)
    except Exception as exc:
        logger.exception("Failed to persist investigation %s", investigation.id)
        # Still return the result — persistence failure isn't user-facing fatal.
        # Log it and move on; the in-memory result is still useful to the caller.

    return investigation


@router.get(
    "/{investigation_id}",
    response_model=Investigation,
    summary="Retrieve an investigation by ID",
)
def get_investigation_by_id(investigation_id: str) -> Investigation:
    investigation = get_investigation(investigation_id)
    if investigation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Investigation '{investigation_id}' not found.",
        )
    return investigation


@router.get(
    "",
    response_model=list[dict],
    summary="List recent investigations (summaries only)",
)
def list_recent_investigations(limit: int = 20) -> list[dict]:
    if limit < 1 or limit > 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="limit must be between 1 and 200.",
        )
    return list_investigations(limit=limit)
