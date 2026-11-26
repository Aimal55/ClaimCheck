# ClaimCheck

Evidence-based claim verification application.

> **Milestone 1 status:** The pipeline is a mock. Results are clearly labelled
> and **must not** be treated as real fact-checks.

---

## Project structure

```
ClaimCheck/
├── backend/
│   ├── main.py                  # FastAPI entry point
│   ├── core/
│   │   ├── config.py            # Typed settings (pydantic-settings)
│   │   └── logging_config.py    # Centralised logging
│   ├── schemas/
│   │   ├── claim.py             # ClaimSubmission, AtomicClaim
│   │   ├── evidence.py          # EvidencePassage
│   │   ├── verdict.py           # Verdict, VerdictLabel
│   │   └── investigation.py     # Investigation (top-level response)
│   ├── services/
│   │   └── mock_pipeline.py     # ⚠️ Mock only — swap for real pipeline later
│   ├── routers/
│   │   └── investigations.py    # POST/GET /api/v1/investigations
│   └── db/
│       └── database.py          # SQLite persistence (plain sqlite3)
├── frontend/
│   └── app.py                   # Streamlit UI
├── tests/
│   ├── test_schemas.py
│   └── test_investigations.py
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Windows setup (PowerShell)

### Prerequisites
- Python 3.11 or newer
- Git

> **Windows note:** `python` on Windows often resolves to the Microsoft Store
> stub (a no-op). Use `py` (the Windows Python Launcher) instead — it always
> routes to a real installation.

### 1 — Clone and enter the project

```powershell
git clone <repo-url> ClaimCheck
cd ClaimCheck
```

### 2 — Verify Python is accessible

```powershell
py --version          # should print Python 3.11.x or newer
```

If `py` is not found, download the official installer from python.org —
make sure "Add python.exe to PATH" and "Install for all users" are checked.

### 3 — Create a virtual environment

```powershell
py -m venv .venv
```

### 4 — Install dependencies (use the venv directly — no activation needed)

```powershell
.\.venv\Scripts\pip.exe install -r requirements.txt
```

### 5 — Configure environment variables

```powershell
Copy-Item .env.example .env
```

Open `.env` in any editor — the defaults work for local development.
**Do not commit `.env` to git.**

---

## Running the application

You need **two terminals**.

### Terminal 1 — FastAPI backend

```powershell
.\.venv\Scripts\uvicorn.exe backend.main:app --reload --host 127.0.0.1 --port 8000
```

- API docs: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health

### Terminal 2 — Streamlit frontend

```powershell
.\.venv\Scripts\streamlit.exe run frontend/app.py
```

- Opens automatically at http://localhost:8501

---

## Running tests

```powershell
.\.venv\Scripts\pytest.exe tests/ -v
```

Tests use an isolated temporary SQLite database — they never touch `claimcheck.db`.

---

## Environment variables reference

| Variable | Default | Description |
|---|---|---|
| `APP_HOST` | `127.0.0.1` | Uvicorn bind address |
| `APP_PORT` | `8000` | Uvicorn port |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `DB_PATH` | `claimcheck.db` | SQLite file path |
| `CLAIM_MIN_LENGTH` | `10` | Minimum claim length |
| `CLAIM_MAX_LENGTH` | `2000` | Maximum claim length |
| `API_BASE_URL` | `http://127.0.0.1:8000` | Used by Streamlit to call the API |

---

## API reference (Milestone 1)

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness probe |
| `POST` | `/api/v1/investigations` | Submit a claim |
| `GET` | `/api/v1/investigations/{id}` | Retrieve an investigation |
| `GET` | `/api/v1/investigations` | List recent investigations |

Interactive docs with request/response schemas: http://127.0.0.1:8000/docs

---

## Mock data notice

The current pipeline (`backend/services/mock_pipeline.py`) returns **hardcoded
fictional evidence and an UNVERIFIED verdict** for every claim.  Every result
has `is_mock: true` and a disclaimer.  The Streamlit UI displays this
prominently.

To replace the mock with a real pipeline:
1. Implement the same function signature in a new service module.
2. Update the import in `backend/routers/investigations.py`.
3. Nothing else needs to change.

---

## Live MVP Pipeline

The live endpoint is:

```text
POST /api/v1/investigations?use_mock=false
```

Default live search uses Wikipedia, which is key-free. For broader web search, set `SEARCH_PROVIDER=tavily` and provide `TAVILY_API_KEY`. Tavily is a paid/credit provider; verify current limits before use.

The live pipeline:

1. Uses Gemini to extract atomic factual claims.
2. Searches sources and extracts readable text with Trafilatura.
3. Creates overlapping chunks with character offsets.
4. Uses BM25 plus Gemini embeddings, fused with reciprocal rank fusion.
5. Optionally uses a cross-encoder reranker when `RERANKER_ENABLED=true` and `sentence-transformers` is installed.
6. Uses Gemini to produce Pydantic-validated evidence verdicts with passage IDs and source URLs.

Mock mode remains available through `use_mock=true` for compatibility and testing.

---

## LangChain and LangGraph integration

Live investigations are compiled as a LangGraph `StateGraph`. The graph separates decomposition, search, extraction/chunking, retrieval, reranking, verification, quality checking, and finalization.

- LangChain `Document` and `RecursiveCharacterTextSplitter` create traceable chunks.
- `langchain-google-genai` provides Pydantic structured Gemini calls.
- Hybrid retrieval combines BM25 and Gemini embeddings using reciprocal rank fusion.
- Cross-encoder reranking is optional; failed or disabled reranking uses hybrid rank ordering.
- Weak evidence receives one additional retrieval attempt. A second weak result becomes `INSUFFICIENT_EVIDENCE`.

Mock mode remains available with `use_mock=true`; live mode is `use_mock=false`.

---

## Development notes

- **Never hardcode API keys.** Add them to `.env` and read via `Settings` in
  `backend/core/config.py`.
- Logging is centralised — use `logging.getLogger(__name__)` in every module.
- Pydantic v2 `model_config = ConfigDict(...)` is used throughout (not the
  deprecated `class Config`).
