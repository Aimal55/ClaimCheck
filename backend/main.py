"""
FastAPI application entry point.

Keep this file thin — it only wires together:
  - logging
  - database initialisation
  - CORS middleware
  - routers
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import settings
from backend.core.logging_config import setup_logging
from backend.db.database import init_db
from backend.routers.investigations import router as investigations_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Run startup / shutdown tasks."""
    setup_logging()
    init_db()
    yield
    # Nothing to clean up yet.


app = FastAPI(
    title="ClaimCheck API",
    description=(
        "Evidence-based claim verification API. "
        "Milestone 1 uses a mock pipeline — results are NOT real fact-checks."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — allow the Streamlit dev server (port 8501) to call this API.
# Restrict origins in production.
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",
        "http://127.0.0.1:8501",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(investigations_router)


@app.get("/health", tags=["meta"])
def health_check() -> dict:
    """Simple liveness probe."""
    return {"status": "ok", "version": app.version}
