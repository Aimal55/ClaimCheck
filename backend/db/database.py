"""
SQLite persistence layer — plain sqlite3, no ORM.

Keeping it simple in milestone 1:  one table, one row per Investigation,
stored as a JSON blob.  This is easy to query manually and easy to migrate
to a proper schema later.

Design note: we store the full Investigation JSON rather than normalising
into multiple tables because the schema is still evolving and round-tripping
JSON is zero-friction for Pydantic models.
"""

import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from backend.core.config import settings
from backend.schemas.investigation import Investigation

logger = logging.getLogger(__name__)

_DB_PATH = Path(settings.db_path)

# --------------------------------------------------------------------- #
# Connection helper                                                       #
# --------------------------------------------------------------------- #

@contextmanager
def _get_connection() -> Generator[sqlite3.Connection, None, None]:
    """Yield a sqlite3 connection with row_factory set."""
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# --------------------------------------------------------------------- #
# Schema initialisation                                                   #
# --------------------------------------------------------------------- #

CREATE_INVESTIGATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS investigations (
    id          TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    status      TEXT NOT NULL,
    is_mock     INTEGER NOT NULL DEFAULT 1,
    data        TEXT NOT NULL   -- full Investigation JSON blob
);
"""

CREATE_LIVE_TABLES = """
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT,
    text TEXT,
    publication_date TEXT,
    retrieved_at TEXT NOT NULL,
    extraction_status TEXT NOT NULL,
    extraction_error TEXT,
    search_snippet TEXT,
    FOREIGN KEY(investigation_id) REFERENCES investigations(id)
);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    atomic_claim_id TEXT NOT NULL,
    text TEXT NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    lexical_score REAL,
    semantic_score REAL,
    fused_score REAL,
    rerank_score REAL,
    FOREIGN KEY(investigation_id) REFERENCES investigations(id),
    FOREIGN KEY(source_id) REFERENCES sources(id)
);

CREATE TABLE IF NOT EXISTS evidence_passages (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL,
    atomic_claim_id TEXT NOT NULL,
    chunk_id TEXT,
    text TEXT NOT NULL,
    source_url TEXT,
    source_title TEXT,
    stance TEXT,
    relevance_score REAL,
    rerank_score REAL,
    is_mock INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(investigation_id) REFERENCES investigations(id),
    FOREIGN KEY(chunk_id) REFERENCES chunks(id)
);
"""


def init_db() -> None:
    """Create tables if they don't already exist. Called once at startup."""
    logger.info("Initialising database at %s", _DB_PATH)
    with _get_connection() as conn:
        conn.execute(CREATE_INVESTIGATIONS_TABLE)
        for statement in CREATE_LIVE_TABLES.split(";"):
            statement = statement.strip()
            if statement:
                conn.execute(statement)
    logger.info("Database ready.")


# --------------------------------------------------------------------- #
# CRUD helpers                                                            #
# --------------------------------------------------------------------- #

def save_investigation(investigation: Investigation) -> None:
    """Persist an Investigation to SQLite."""
    with _get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO investigations (id, created_at, status, is_mock, data)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                investigation.id,
                investigation.created_at.isoformat(),
                investigation.status.value,
                int(investigation.is_mock),
                investigation.model_dump_json(),
            ),
        )

        for source in getattr(investigation, "sources", []):
            conn.execute(
                """
                INSERT OR REPLACE INTO sources
                (id, investigation_id, url, title, text, publication_date, retrieved_at,
                 extraction_status, extraction_error, search_snippet)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source.id,
                    investigation.id,
                    source.url,
                    source.title,
                    source.text,
                    source.publication_date,
                    source.retrieved_at.isoformat(),
                    source.extraction_status,
                    source.extraction_error,
                    source.search_snippet,
                ),
            )

        for chunk in getattr(investigation, "chunks", []):
            conn.execute(
                """
                INSERT OR REPLACE INTO chunks
                (id, investigation_id, source_id, atomic_claim_id, text, char_start, char_end,
                 lexical_score, semantic_score, fused_score, rerank_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk.id,
                    investigation.id,
                    chunk.source_id,
                    chunk.atomic_claim_id,
                    chunk.text,
                    chunk.char_start,
                    chunk.char_end,
                    chunk.lexical_score,
                    chunk.semantic_score,
                    chunk.fused_score,
                    chunk.rerank_score,
                ),
            )

        for passage in investigation.evidence_passages:
            if passage.is_mock:
                continue
            conn.execute(
                """
                INSERT OR REPLACE INTO evidence_passages
                (id, investigation_id, atomic_claim_id, chunk_id, text, source_url,
                 source_title, stance, relevance_score, rerank_score, is_mock)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    passage.id,
                    investigation.id,
                    passage.atomic_claim_id,
                    passage.chunk_id,
                    passage.text,
                    passage.source_url,
                    passage.source_title,
                    passage.stance,
                    passage.relevance_score,
                    passage.rerank_score,
                ),
            )
    logger.debug("Saved investigation %s", investigation.id)


def get_investigation(investigation_id: str) -> Investigation | None:
    """Return an Investigation by ID, or None if not found."""
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT data FROM investigations WHERE id = ?", (investigation_id,)
        ).fetchone()

    if row is None:
        return None

    return Investigation.model_validate_json(row["data"])


def list_investigations(limit: int = 50) -> list[dict]:
    """Return lightweight summary rows (id, created_at, status, is_mock)."""
    with _get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, created_at, status, is_mock, data
            FROM investigations
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    summaries: list[dict] = []
    for row in rows:
        summary = dict(row)
        data = summary.pop("data")
        try:
            investigation = Investigation.model_validate_json(data)
            summary["submission_text"] = investigation.submission.text
            summary["verdict_label"] = (
                investigation.verdicts[0].label.value
                if investigation.verdicts
                else None
            )
        except Exception:
            summary["submission_text"] = None
            summary["verdict_label"] = None
        summaries.append(summary)
    return summaries
