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


def init_db() -> None:
    """Create tables if they don't already exist. Called once at startup."""
    logger.info("Initialising database at %s", _DB_PATH)
    with _get_connection() as conn:
        conn.execute(CREATE_INVESTIGATIONS_TABLE)
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
            SELECT id, created_at, status, is_mock
            FROM investigations
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
