"""Webpage extraction and source normalization using Trafilatura."""

import logging
from datetime import datetime, timezone

import requests
import trafilatura

logger = logging.getLogger(__name__) 


class SourceExtractor:
    def __init__(self, timeout: float = 12.0) -> None:
        self.timeout = timeout

    def extract(self, url: str, fallback_title: str | None = None, snippet: str = ""):
        from backend.schemas.source import EvidenceSource

        retrieved_at = datetime.now(timezone.utc)
        try:
            response = requests.get(
                url,
                timeout=self.timeout,
                headers={"User-Agent": "ClaimCheck/1.0 (educational research app)"},
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            return EvidenceSource(
                url=url,
                title=fallback_title,
                text=None,
                publication_date=None,
                retrieved_at=retrieved_at,
                extraction_status="unavailable",
                extraction_error=str(exc.__class__.__name__),
                search_snippet=snippet,
            )

        try:
            downloaded = trafilatura.extract(
                response.text,
                url=url,
                include_comments=False,
                include_tables=True,
                output_format="txt",
                with_metadata=True,
            )
            metadata = trafilatura.extract_metadata(response.text, default_url=url)
        except Exception as exc:
            downloaded = None
            metadata = None
            logger.warning("Extraction failed for %s", url)

        if not downloaded:
            downloaded = None

        title = fallback_title
        publication_date = None
        if metadata is not None:
            title = getattr(metadata, "title", None) or title
            publication_date = getattr(metadata, "date", None)

        status = "extracted" if downloaded else "no_readable_text"
        return EvidenceSource(
            url=url,
            title=title,
            text=downloaded,
            publication_date=publication_date,
            retrieved_at=retrieved_at,
            extraction_status=status,
            extraction_error=None if downloaded else "No readable text found.",
            search_snippet=snippet,
        )
