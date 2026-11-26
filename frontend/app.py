"""
ClaimCheck — Streamlit frontend (Milestone 1)

Submits a claim to the FastAPI backend and renders the mock investigation
result with a prominent disclaimer.
"""

import os

import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Configuration — read from environment or fall back to defaults
# ---------------------------------------------------------------------------
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
INVESTIGATIONS_URL = f"{API_BASE_URL}/api/v1/investigations?use_mock=false"
REQUEST_TIMEOUT_SECONDS = 180

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="ClaimCheck",
    page_icon="🔍",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Custom CSS — minimal, keeps the page readable
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    .mock-banner {
        background: #fff3cd;
        border-left: 5px solid #ffc107;
        padding: 0.75rem 1rem;
        border-radius: 4px;
        font-size: 0.9rem;
        color: #856404;
        margin-bottom: 1rem;
    }
    .verdict-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 999px;
        font-weight: 700;
        font-size: 1rem;
        letter-spacing: 0.05em;
    }
    .verdict-UNVERIFIED       { background:#e9ecef; color:#495057; }
    .verdict-SUPPORTED        { background:#d4edda; color:#155724; }
    .verdict-REFUTED          { background:#f8d7da; color:#721c24; }
    .verdict-INSUFFICIENT_EVIDENCE { background:#fff3cd; color:#856404; }
    .verdict-CONFLICTING_EVIDENCE  { background:#fde2c8; color:#7a3e00; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("🔍 ClaimCheck")
st.caption("Evidence-based claim verification · Live Gemini + retrieval pipeline")
st.divider()

# ---------------------------------------------------------------------------
# Input form
# ---------------------------------------------------------------------------
with st.form("claim_form", clear_on_submit=False):
    claim_text = st.text_area(
        label="Enter a factual claim to investigate",
        placeholder="e.g. The Great Wall of China is visible from space with the naked eye.",
        height=120,
        max_chars=2000,
        help="Between 10 and 2000 characters.",
    )
    submitted = st.form_submit_button("🔎 Investigate", use_container_width=True)

# ---------------------------------------------------------------------------
# Submit & render
# ---------------------------------------------------------------------------
if submitted:
    claim_text = claim_text.strip()

    # --- Client-side validation (mirrors backend limits) ------------------
    if len(claim_text) < 10:
        st.error("⚠️ Please enter at least 10 characters.")
        st.stop()

    # --- Call the API -----------------------------------------------------
    with st.spinner("Contacting backend…"):
        try:
            response = requests.post(
                INVESTIGATIONS_URL,
                json={"text": claim_text},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except requests.exceptions.ConnectionError:
            st.error(
                "❌ **Could not connect to the backend.** "
                f"Make sure the API is running at `{API_BASE_URL}`."
            )
            st.stop()
        except requests.exceptions.Timeout:
            st.error("❌ **Request timed out.** The backend took too long to respond.")
            st.stop()
        except requests.exceptions.HTTPError as exc:
            # FastAPI returns structured JSON errors — try to surface them.
            try:
                detail = exc.response.json().get("detail", str(exc))
            except Exception:
                detail = str(exc)
            st.error(f"❌ **API error ({exc.response.status_code}):** {detail}")
            st.stop()

    data = response.json()

    # --- Mock disclaimer --------------------------------------------------
    if data.get("is_mock"):
        disclaimer = data.get("mock_disclaimer", "Results are mock data.")
        st.markdown(
            f'<div class="mock-banner">🧪 <strong>MOCK DATA</strong> — {disclaimer}</div>',
            unsafe_allow_html=True,
        )

    # --- Provider status ------------------------------------------------
    if data.get("is_mock"):
        st.caption("🧪 Current result: mock pipeline")
    else:
        st.success("✅ Live Gemini decomposition and evidence assessment")

    # --- Investigation metadata ------------------------------------------
    st.subheader("📋 Investigation")
    col1, col2 = st.columns(2)
    col1.metric("ID", data["id"][:8] + "…")
    col2.metric("Status", data["status"])

    # --- Verdict ---------------------------------------------------------
    st.subheader("⚖️ Verdict")
    for verdict in data.get("verdicts", []):
        label = verdict["label"]
        badge_html = (
            f'<span class="verdict-badge verdict-{label}">{label.replace("_", " ")}</span>'
        )
        st.markdown(badge_html, unsafe_allow_html=True)
        st.markdown(f"> {verdict['explanation']}")
        if verdict.get("confidence") is not None:
            st.caption(f"Confidence: {verdict['confidence']:.2f}")
        if verdict.get("supporting_passage_ids"):
            st.caption("Supporting passage IDs: " + ", ".join(verdict["supporting_passage_ids"]))
        if verdict.get("refuting_passage_ids"):
            st.caption("Refuting passage IDs: " + ", ".join(verdict["refuting_passage_ids"]))
        if verdict.get("cited_source_urls"):
            for url in verdict["cited_source_urls"]:
                st.markdown(f"🔗 [{url}]({url})")
        if verdict.get("limitations"):
            st.warning(verdict["limitations"])
        if verdict.get("is_mock"):
            st.caption("🧪 This verdict was produced by the mock pipeline.")

    # --- Sources --------------------------------------------------------
    st.subheader("🔎 Sources")
    sources = data.get("sources", [])
    if not sources:
        st.info("No sources were recorded.")
    else:
        for source in sources:
            with st.expander(source.get("title") or source["url"]):
                st.markdown(f"[Open source]({source['url']})")
                st.caption(f"Status: {source.get('extraction_status', 'unknown')}")
                if source.get("publication_date"):
                    st.caption(f"Published: {source['publication_date']}")
                if source.get("retrieved_at"):
                    st.caption(f"Retrieved: {source['retrieved_at']}")
                if source.get("extraction_error"):
                    st.warning(source["extraction_error"])

    # --- Evidence passages -----------------------------------------------
    st.subheader("📚 Evidence Passages")
    passages = data.get("evidence_passages", [])
    if not passages:
        st.info("No evidence passages returned.")
    else:
        for i, passage in enumerate(passages, start=1):
            with st.expander(
                f"Passage {i} — {passage.get('source_title', 'Unknown source')} "
                f"(relevance: {passage.get('relevance_score', 'N/A')})",
                expanded=(i == 1),
            ):
                st.write(passage["text"])
                if passage.get("source_url"):
                    st.markdown(f"🔗 [Source]({passage['source_url']})")
                if passage.get("is_mock"):
                    st.caption("🧪 Mock passage — not retrieved from a real source.")

    # --- Atomic claims --------------------------------------------------
    st.subheader("🧩 Extracted Atomic Claims")
    atomic_claims = data.get("atomic_claims", [])
    if not atomic_claims:
        st.info("No independently verifiable factual claims were extracted.")
    else:
        for i, claim in enumerate(atomic_claims, start=1):
            with st.expander(f"Claim {i}: {claim['text']}", expanded=(i == 1)):
                st.write(claim["text"])
                if claim.get("claim_type"):
                    st.caption(f"Claim type: {claim['claim_type']}")
                if claim.get("entities"):
                    st.caption("Entities: " + ", ".join(claim["entities"]))
                if claim.get("temporal_context"):
                    st.caption(f"Time: {claim['temporal_context']}")
                if claim.get("geographic_context"):
                    st.caption(f"Location: {claim['geographic_context']}")
                if claim.get("search_queries"):
                    st.markdown("**Suggested searches**")
                    for query in claim["search_queries"]:
                        st.markdown(f"- {query}")

    # --- Raw JSON (dev helper) -------------------------------------------
    with st.expander("🛠 Raw API response (debug)", expanded=False):
        st.json(data)

# ---------------------------------------------------------------------------
# Investigation history
# ---------------------------------------------------------------------------
st.sidebar.header("History")
try:
    history_response = requests.get(
        f"{API_BASE_URL}/api/v1/investigations?limit=20",
        timeout=10,
    )
    history_response.raise_for_status()
    history = history_response.json()
    if history:
        for item in history:
            st.sidebar.markdown(
                f"`{item['id'][:8]}…` · {item['status']} · "
                f"{'mock' if item['is_mock'] else 'live'}"
            )
    else:
        st.sidebar.info("No investigations yet.")
except requests.RequestException:
    st.sidebar.warning("History unavailable while backend is offline.")
