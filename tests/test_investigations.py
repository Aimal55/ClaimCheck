"""
Integration tests for the investigations endpoints.

Uses FastAPI's TestClient (wraps httpx) — no live server needed.
The database is redirected to a temporary file so tests don't pollute the
dev database.
"""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

# Point the DB at a temp file BEFORE importing the app so database.py picks
# up the override through settings.
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()
os.environ["DB_PATH"] = _tmp_db.name

from backend.main import app  # noqa: E402  (import after env override)
from backend.db.database import init_db  # noqa: E402
from backend.core.config import settings  # noqa: E402

init_db()
client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def post_claim(text: str) -> dict:
    response = client.post("/api/v1/investigations", json={"text": text})
    return response


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_ok(self):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# POST /api/v1/investigations — happy path
# ---------------------------------------------------------------------------

class TestCreateInvestigation:
    def test_happy_path_returns_201(self):
        r = post_claim("The Great Wall of China is visible from space.")
        assert r.status_code == 201

    def test_response_has_required_fields(self):
        r = post_claim("Water freezes at zero degrees Celsius at standard pressure.")
        data = r.json()
        assert "id" in data
        assert "submission" in data
        assert "verdicts" in data
        assert "evidence_passages" in data
        assert "status" in data

    def test_mock_flag_is_true(self):
        r = post_claim("The moon is made of green cheese, according to some.")
        data = r.json()
        assert data["is_mock"] is True

    def test_mock_disclaimer_present(self):
        r = post_claim("Light travels faster than sound in all conditions tested.")
        data = r.json()
        assert data["mock_disclaimer"] is not None
        assert len(data["mock_disclaimer"]) > 0

    def test_verdict_label_is_unverified(self):
        r = post_claim("Coffee is consumed more than tea worldwide across all regions.")
        data = r.json()
        assert data["verdicts"][0]["label"] == "UNVERIFIED"

    def test_evidence_passages_returned(self):
        r = post_claim("The Amazon is the longest river in the entire world.")
        data = r.json()
        assert len(data["evidence_passages"]) >= 1

    def test_submission_text_round_trips(self):
        claim = "Diamonds are the hardest naturally occurring substance on Earth."
        r = post_claim(claim)
        assert r.json()["submission"]["text"] == claim


# ---------------------------------------------------------------------------
# POST — validation errors
# ---------------------------------------------------------------------------

class TestCreateInvestigationValidation:
    def test_empty_string_returns_422(self):
        r = client.post("/api/v1/investigations", json={"text": ""})
        assert r.status_code == 422

    def test_too_short_returns_422(self):
        r = client.post("/api/v1/investigations", json={"text": "Too short"})
        assert r.status_code == 422

    def test_too_long_returns_422(self):
        r = client.post("/api/v1/investigations", json={"text": "x" * 2001})
        assert r.status_code == 422

    def test_missing_text_field_returns_422(self):
        r = client.post("/api/v1/investigations", json={})
        assert r.status_code == 422

    def test_whitespace_only_returns_422(self):
        r = client.post("/api/v1/investigations", json={"text": "     "})
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/investigations/{id}
# ---------------------------------------------------------------------------

class TestGetInvestigation:
    def test_get_existing_returns_200(self):
        create_r = post_claim("Humans use only ten percent of their brain capacity.")
        investigation_id = create_r.json()["id"]

        get_r = client.get(f"/api/v1/investigations/{investigation_id}")
        assert get_r.status_code == 200
        assert get_r.json()["id"] == investigation_id

    def test_get_nonexistent_returns_404(self):
        r = client.get("/api/v1/investigations/does-not-exist-xyz")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/v1/investigations (list)
# ---------------------------------------------------------------------------

class TestListInvestigations:
    def test_list_returns_200(self):
        r = client.get("/api/v1/investigations")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_limit_too_large_returns_400(self):
        r = client.get("/api/v1/investigations?limit=999")
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Gemini mode tests
# ---------------------------------------------------------------------------

class TestGeminiMode:
    def test_missing_api_key_returns_503(self):
        old_key = settings.gemini_api_key
        settings.gemini_api_key = ""
        try:
            r = client.post(
                "/api/v1/investigations?use_mock=false",
                json={"text": "Water freezes at zero degrees Celsius."},
            )
            assert r.status_code == 503
            assert "GEMINI_API_KEY" in r.json()["detail"]
        finally:
            settings.gemini_api_key = old_key

    def test_mock_mode_remains_available(self):
        r = client.post(
            "/api/v1/investigations?use_mock=true",
            json={"text": "Water freezes at zero degrees Celsius."},
        )
        assert r.status_code == 201
        assert r.json()["is_mock"] is True
