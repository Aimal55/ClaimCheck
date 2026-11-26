"""ClaimCheck premium Streamlit dashboard for live and mock investigations."""

import os
from datetime import datetime
from urllib.parse import urlparse

import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
INVESTIGATIONS_URL = f"{API_BASE_URL}/api/v1/investigations?use_mock=false"
REQUEST_TIMEOUT_SECONDS = 180

st.set_page_config(page_title="ClaimCheck", page_icon="C", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
:root { --bg:#0b0d12; --surface:#11151e; --surface2:#171b27; --border:#252b3a; --text:#f4f6fb; --muted:#99a1b3; --violet:#7c6df2; --green:#49c78e; --red:#ee7a82; --amber:#e7b84b; }
html, body, [class*="css"] { background:var(--bg); color:var(--text); }
[data-testid="stAppViewContainer"] { background: radial-gradient(circle at 75% 0%, rgba(124,109,242,.07), transparent 28%), var(--bg); }
[data-testid="stHeader"] { background:transparent; }
[data-testid="stSidebar"] { background:#0f1219; border-right:1px solid var(--border); }
.block-container { max-width:1180px; padding-top:2.4rem; }
.brand { display:flex; align-items:center; gap:.65rem; font-size:1.05rem; font-weight:750; }
.brand-mark { width:34px; height:34px; border:1px solid #5149a7; border-radius:9px; background:#19172b; display:grid; place-items:center; color:#bdb6ff; font-weight:800; }
.hero { padding:.55rem 0 1.4rem; }
.hero h1 { margin:0; font-size:2.65rem; letter-spacing:-.045em; line-height:1.05; }
.hero p { color:var(--muted); font-size:1.05rem; max-width720px; }
.card { background:var(--surface); border:1px solid var(--border); border-radius:14px; padding:1.15rem 1.25rem; box-shadow:0 14px 36px rgba(0,0,0,.12); }
.soft-card { background:var(--surface2); border:1px solid var(--border); border-radius:12px; padding:.85rem 1rem; }
.status-row { display:flex; align-items:center; gap:.5rem; color:var(--muted); font-size:.82rem; }
.status-dot { width:8px; height:8px; border-radius:50%; background:var(--green); box-shadow:0 0 10px rgba(73,199,142,.45); }
.verdict { border-radius:14px; padding:1.15rem 1.25rem; border:1px solid var(--border); }
.verdict-SUPPORTED { background:rgba(73,199,142,.08); border-color:rgba(73,199,142,.34); }
.verdict-REFUTED { background:rgba(238,122,130,.08); border-color:rgba(238,122,130,.34); }
.verdict-CONFLICTING_EVIDENCE { background:rgba(231,184,75,.08); border-color:rgba(231,184,75,.34); }
.verdict-INSUFFICIENT_EVIDENCE,.verdict-UNVERIFIED { background:rgba(153,161,179,.07); border-color:var(--border); }
.verdict-label { font-size:.72rem; letter-spacing:.12em; text-transform:uppercase; color:var(--muted); font-weight:800; }
.verdict-title { font-size:1.45rem; margin:.2rem 0 .35rem; }
.domain { color:var(--muted); font-size:.78rem; text-transform:uppercase; letter-spacing:.04em; }
.passage { line-height:1.55; color:#dfe3ec; }
.meta { color:var(--muted); font-size:.82rem; }
.no-evidence { border:1px dashed var(--border); border-radius:12px; padding:1.25rem; color:var(--muted); text-align:center; }
.small { color:var(--muted); font-size:.82rem; }
.stTextArea textarea { min-height:150px; background:#121620 !important; border:1px solid var(--border) !important; border-radius:12px !important; }
.stButton>button { border-radius:9px; min-height:44px; border:1px solid #6258ca; }
[data-testid="stSidebarNav"] { display:none; }
</style>
""", unsafe_allow_html=True)

if "page" not in st.session_state:
    st.session_state.page = "New Investigation"
if "claim_text" not in st.session_state:
    st.session_state.claim_text = ""
if "report" not in st.session_state:
    st.session_state.report = None


def get_domain(url):
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return "source"


def safe_request(method, url, timeout=12, **kwargs):
    try:
        response = requests.request(method, url, timeout=timeout, **kwargs)
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.Timeout:
        return None, "The backend request timed out."
    except requests.exceptions.ConnectionError:
        return None, "The backend is unavailable."
    except requests.exceptions.HTTPError as exc:
        try:
            detail = exc.response.json().get("detail")
        except Exception:
            detail = None
        return None, detail or "The request could not be completed."
    except requests.RequestException:
        return None, "The API returned an unexpected response."


def sidebar():
    with st.sidebar:
        st.markdown('<div class="brand"><div class="brand-mark">C</div><span>ClaimCheck</span></div>', unsafe_allow_html=True)
        st.caption("Evidence intelligence workspace")
        st.markdown("")
        for label in ("New Investigation", "History", "About"):
            if st.button(label, key=f"nav_{label}", use_container_width=True):
                st.session_state.page = label
        st.markdown("<hr style='border-color:#252b3a'>", unsafe_allow_html=True)
        health, health_error = safe_request("GET", f"{API_BASE_URL}/health", 5)
        if health_error:
            st.markdown('<div class="status-row"><span class="status-dot" style="background:#ee7a82"></span>Backend offline</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="status-row"><span class="status-dot"></span>Backend online</div>', unsafe_allow_html=True)
        st.caption("Live Gemini + evidence retrieval" if not health_error else "Live services unavailable")


def verdict_banner(report):
    verdicts = report.get("verdicts", [])
    if not verdicts:
        st.markdown('<div class="verdict verdict-UNVERIFIED"><div class="verdict-label">Verdict unavailable</div><div class="verdict-title">Insufficient evidence</div><p class="meta">No verdict was produced.</p></div>', unsafe_allow_html=True)
        return
    verdict = verdicts[0]
    label = verdict.get("label", "INSUFFICIENT_EVIDENCE")
    title = label.replace("_", " ").title()
    st.markdown(f'<div class="verdict verdict-{label}"><div class="verdict-label">Final verdict</div><div class="verdict-title">{title}</div><div class="meta">{verdict.get("explanation", "No explanation available.")}</div></div>', unsafe_allow_html=True)
    confidence = verdict.get("confidence")
    if isinstance(confidence, (int, float)):
        confidence = max(0.0, min(1.0, float(confidence)))
        st.caption("Model confidence — not a calibrated probability")
        st.progress(confidence)
    if verdict.get("limitations"):
        st.warning(verdict["limitations"])


def claim_cards(report):
    claims = report.get("atomic_claims", [])
    st.subheader("Atomic claims")
    if not claims:
        st.markdown('<div class="no-evidence">No independently verifiable factual claims were extracted.</div>', unsafe_allow_html=True)
        return
    for index, claim in enumerate(claims, 1):
        with st.container(border=True):
            st.markdown(f"**Claim {index}**")
            st.write(claim.get("text", ""))
            details = []
            if claim.get("claim_type"):
                details.append(claim["claim_type"])
            if claim.get("temporal_context"):
                details.append(claim["temporal_context"])
            if claim.get("geographic_context"):
                details.append(claim["geographic_context"])
            if details:
                st.caption(" · ".join(details))


def evidence_cards(report):
    verdicts = report.get("verdicts", [])
    verdict = verdicts[0] if verdicts else {}
    supporting = set(verdict.get("supporting_passage_ids", []))
    refuting = set(verdict.get("refuting_passage_ids", []))
    passages = report.get("evidence_passages", [])
    st.subheader("Evidence")
    if not passages:
        st.markdown('<div class="no-evidence">No extracted evidence passages are available. This is insufficient evidence, not a factual conclusion.</div>', unsafe_allow_html=True)
        return
    sources = {source.get("id"): source for source in report.get("sources", [])}
    for passage in passages:
        stance = "Supporting" if passage.get("id") in supporting else "Refuting" if passage.get("id") in refuting else "Context"
        source_url = passage.get("source_url")
        title = passage.get("source_title") or (get_domain(source_url) if source_url else "Unknown source")
        with st.container(border=True):
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(f"**{title}**")
                st.markdown(f'<div class="domain">{stance} · {get_domain(source_url) if source_url else "No source URL"}</div>', unsafe_allow_html=True)
            with col2:
                if passage.get("relevance_score") is not None:
                    st.metric("Rank score", f"{float(passage['relevance_score']):.2f}")
            st.markdown(f'<div class="passage">{passage.get("text", "")}</div>', unsafe_allow_html=True)
            if source_url:
                st.link_button("Open source", source_url)


def report_view(report):
    verdict_banner(report)
    st.markdown("")
    claim_cards(report)
    evidence_cards(report)
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Pipeline status**")
        st.caption("Complete" if report.get("status") == "COMPLETE" else report.get("status", "Unknown"))
    with col2:
        st.markdown("**Investigation**")
        st.caption(report.get("id", "Unknown")[:16])
    with st.expander("Technical details and retrieval scores"):
        for source in report.get("sources", []):
            st.markdown(f"**{source.get('title') or source.get('url')}**")
            st.caption(f"Status: {source.get('extraction_status', 'unknown')}")
            if source.get("publication_date"):
                st.caption(f"Publication date: {source['publication_date']}")
            if source.get("retrieved_at"):
                st.caption(f"Retrieved: {source['retrieved_at']}")
    with st.expander("Raw API response"):
        st.json(report)


sidebar()

if st.session_state.page == "New Investigation":
    st.markdown('<div class="hero"><h1>Verify what matters.</h1><p>Investigate a factual claim through evidence extraction, retrieval, and model-assisted verification.</p></div>', unsafe_allow_html=True)

    examples = [
        "The Great Wall of China is visible from space with the naked eye.",
        "Water boils at 100°C at standard atmospheric pressure.",
        "Humans use only 10 percent of their brain.",
    ]
    cols = st.columns(3)
    for index, example in enumerate(examples):
        if cols[index].button(example[:34] + "…", key=f"example_{index}", use_container_width=True):
            st.session_state.claim_text = example

    claim_text = st.text_area("Claim", value=st.session_state.claim_text, height=150, max_chars=2000, placeholder="Enter a specific, factual claim…")
    st.session_state.claim_text = claim_text

    left, right = st.columns([1, 4])
    with left:
        submitted = st.button("Investigate Claim", type="primary", use_container_width=True)
    with right:
        st.markdown('<div class="status-row"><span>Evidence quality varies by source availability.</span></div>', unsafe_allow_html=True)

    if submitted:
        claim_text = claim_text.strip()
        if len(claim_text) < 10:
            st.error("Enter at least 10 characters.")
        elif len(claim_text) > 2000:
            st.error("Claims cannot exceed 2000 characters.")
        else:
            with st.spinner("Decomposing claim and retrieving evidence…"):
                data, error = safe_request("POST", INVESTIGATIONS_URL, REQUEST_TIMEOUT_SECONDS, json={"text": claim_text})
            if error:
                st.error(error)
            elif data:
                st.session_state.report = data

    if st.session_state.report:
        st.markdown("")
        report_view(st.session_state.report)

elif st.session_state.page == "History":
    st.markdown('<div class="hero"><h1>Investigation history.</h1><p>Review previously saved reports and open complete investigation records.</p></div>', unsafe_allow_html=True)
    history, error = safe_request("GET", f"{API_BASE_URL}/api/v1/investigations?limit=50", 12)
    if error:
        st.error(error)
    elif not history:
        st.markdown('<div class="no-evidence">No investigations have been saved yet.</div>', unsafe_allow_html=True)
    else:
        for item in history:
            created = item.get("created_at")
            if created:
                try:
                    created = datetime.fromisoformat(created.replace("Z", "+00:00")).strftime("%d %b %Y · %H:%M")
                except Exception:
                    created = str(created)
            claim_preview = item.get("submission_text") or "Saved investigation"
            verdict_label = item.get("verdict_label") or ("Mock" if item.get("is_mock") else "Processing")
            with st.container(border=True):
                c1, c2 = st.columns([5, 1])
                with c1:
                    st.markdown(f"**{claim_preview[:180]}**")
                    st.caption(f"{created} · {verdict_label.replace('_', ' ')}")
                with c2:
                    if st.button("Open", key=f"open_{item['id']}", use_container_width=True):
                        report, detail_error = safe_request("GET", f"{API_BASE_URL}/api/v1/investigations/{item['id']}", 12)
                        if detail_error:
                            st.error(detail_error)
                        else:
                            st.session_state.report = report
                            st.session_state.page = "New Investigation"
                            st.rerun()

else:
    st.markdown('<div class="hero"><h1>About ClaimCheck.</h1><p>ClaimCheck separates atomic factual claims, retrieves evidence, and produces model-assisted verdicts with citations.</p></div>', unsafe_allow_html=True)
    st.markdown("""
<div class="card">
<strong>Evidence-based approach</strong>
<p class="small">Supported, refuted, conflicting, and insufficient evidence labels are based on retrieved passages. Model-generated outputs can be wrong.</p>
<p class="small">Inspect the cited sources before relying on a result.</p>
</div>
""", unsafe_allow_html=True)
    st.markdown("")
    st.markdown("**Implemented**")
    st.markdown("- LangGraph live pipeline, Gemini structured output, Tavily search, Trafilatura extraction, BM25 and Gemini embeddings, reciprocal rank fusion, and SQLite history.")
    st.markdown("**Optional or fallback**")
    st.markdown("- Cross-encoder reranking is optional. BM25 remains available when embeddings or reranking are unavailable.")
