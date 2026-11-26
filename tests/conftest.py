"""
pytest configuration and shared fixtures for the ClaimCheck test suite.

IMPORTANT — import order:
  pytest_configure() runs before ANY test module is imported, so setting
  DB_PATH here guarantees that pydantic-settings reads the temp path when
  it first constructs the Settings() singleton (which happens on the first
  import of backend.core.config).
"""

import os
import tempfile

import pytest


# ---------------------------------------------------------------------------
# Set test DB path as early as possible — before backend modules are loaded
# ---------------------------------------------------------------------------

def pytest_configure(config: pytest.Config) -> None:
    """Hook called by pytest before collection. Sets the temp DB path."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    os.environ["DB_PATH"] = tmp.name
    # Store path on config object so pytest_unconfigure can clean it up.
    config._test_db_path = tmp.name  # type: ignore[attr-defined]


def pytest_unconfigure(config: pytest.Config) -> None:
    """Hook called after all tests finish. Removes the temp DB file."""
    path = getattr(config, "_test_db_path", None)
    if path and os.path.exists(path):
        try:
            os.unlink(path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Session-scoped TestClient fixture
#
# Using 'with TestClient(app)' (context manager) is essential — it triggers
# FastAPI's lifespan, which calls setup_logging() and init_db().
# A bare TestClient(app) at module level does NOT start the lifespan.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def app_client():
    """
    Provide a FastAPI TestClient for the full test session.

    The context manager form starts the app lifespan (init_db etc.)
    on enter and shuts it down on exit.
    """
    from fastapi.testclient import TestClient

    from backend.main import app

    with TestClient(app) as client:
        yield client
