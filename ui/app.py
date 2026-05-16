"""Streamlit UI for the Mortgage Multi-Agent Processing Pipeline."""
import json
import sys
from pathlib import Path

import streamlit as st

# Ensure project root is on the path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.orchestrator import LoanPipeline  # noqa: E402

DATA_DIR = ROOT / "mortgage_data" / "sample_loans"

SAMPLE_LOANS = {
    "loan_001 — Clean (APPROVED)": "loan_001_clean.json",
    "loan_002 — Income Mismatch (REVIEW)": "loan_002_income_mismatch.json",
    "loan_003 — CD Imbalance (REJECTED)": "loan_003_cd_imbalance.json",
}

AGENT_ORDER = [
    "document_classifier",
    "income_verifier",
    "appraisal_analyzer",
    "trid_compliance",
    "cd_balancer",
]

STATUS_COLORS = {
    "pass": "#28a745",
    "flag": "#ffc107",
    "reject": "#dc3545",
    "skip": "#6c757d",
}

DECISION_COLORS = {
    "APPROVED": "#28a745",
    "REVIEW": "#ffc107",
    "REJECTED": "#dc3545",
}

MERMAID_GRAPH = """
graph TD
    classify[Document Classifier] --> income[Income Verifier]
    income -->|flag/reject| review[Human Review]
    income -->|pass| appraisal[Appraisal Analyzer]
    appraisal -->|reject| reject_node[Rejection]
    appraisal -->|pass| trid[TRID Compliance]
    trid -->|flag/reject| review
    trid -->|pass| cd[CD Balancer]
    cd -->|reject| reject_node
    cd -->|pass| approve[Approval]
    review --> END([END])
    reject_node --> END
    approve --> END
"""

# ---- Page config ----
st.set_page_config(
    page_title="Mortgage AI Pipeline",
    page_icon="🏠",
    layout="wide",
)
st.title("🏠 Mortgage Multi-Agent Processing Pipeline")
st.caption(
    "LangGraph-powered | 5 specialized agents | Rule-based decisioning | Full audit trail"
)

# ---- Sidebar ----
with st.sidebar:
    st.header("Load Loan Package")
    input_mode = st.radio("Input source", ["Sample loan", "Upload JSON"])

    loan_data: dict | None = None

    if input_mode == "Sample loan":
        choice = st.selectbox("Select sample loan", list(SAMPLE_LOANS.keys()))
        if st.button("Load Sample", use_container_width=True):
            filepath = DATA_DIR / SAMPLE_LOANS[choice]
            with open(filepath) as f:
                loan_data = json.load(f)
            st.session_state["loan_data"] = loan_data
            st.success(f"Loaded {SAMPLE_LOANS[choice]}")
    else:
        uploaded = st.file_uploader("Upload loan JSON", type="json")
        if uploaded:
            loan_data = json.load(uploaded)
            st.session_state["loan_data"] = loan_data
            st.success("File loaded")

    if "loan_data" in st.session_state:
        ld = st.session_state["loan_data"]
        st.markdown("---")
        st.markdown(f"**Loan ID:** {ld.get('loan_id', 'N/A')}")
        borrower = ld.get("application", {}).get("borrower", {})
        st.markdown(f"**Borrower:** {borrower.get('name', 'N/A')}")
        st.markdown(
            f"**Stated Income:** ${borrower.get('annual_income_stated', 0):,.0f}"
        )
        prop = ld.get("application", {}).get("property", {})
        st.markdown(f"**Loan Amount:** ${ld.get('application', {}).get('loan_amount', 0):,.0f}")
        st.markdown(f"**Purchase Price:** ${prop.get('purchase_price', 0):,.0f}")

# ---- Main area ----
if "loan_data" not in st.session_state:
    st.info("Use the sidebar to load a sample loan or upload your own loan JSON.")
    st.stop()

loan_data = st.session_state["loan_data"]

if st.button("Run Pipeline", type="primary", use_container_width=True):
    progress = st.progress(0, text="Starting pipeline...")
    pipeline = LoanPipeline()

    steps = ["Classifying documents...", "Verifying income...",
             "Analyzing appraisal...", "Checking TRID compliance...",
             "Balancing closing disclosure..."]
    for i, step_text in enumerate(steps):
        progress.progress((i + 1) / len(steps), text=step_text)

    with st.spinner("Running all agents..."):
        result = pipeline.run(
            loan_id=loan_data["loan_id"],
            application=loan_data["application"],
            documents=loan_data["documents"],
        )

    progress.progress(1.0, text="Pipeline complete!")
    st.session_state["result"] = result

if "result" not in st.session_state:
    st.stop()

result = st.session_state["result"]
state = result["state"]
findings_map = state.get("agent_findings", {})
decision = state.get("final_decision", "UNKNOWN")

# ---- Final decision banner ----
color = DECISION_COLORS.get(decision, "#6c757d")
st.markdown(
    f"""
    <div style="background:{color}22; border:2px solid {color}; border-radius:8px;
                padding:16px; text-align:center; margin:12px 0;">
        <span style="font-size:2rem; font-weight:bold; color:{color};">{decision}</span>
        <br/>
        <span style="font-size:0.9rem; color:#555;">
            {" | ".join(state.get("decision_reasons", []) or ["No issues flagged."])}
        </span>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---- Agent cards ----
st.subheader("Agent Results")
cols = st.columns(len(AGENT_ORDER))
for col, agent_key in zip(cols, AGENT_ORDER):
    finding = findings_map.get(agent_key, {})
    status = finding.get("status", "skip")
    confidence = finding.get("confidence", 0.0)
    agent_findings_list = finding.get("findings", [])
    color = STATUS_COLORS.get(status, "#6c757d")
    label = agent_key.replace("_", " ").title()
    top_finding = agent_findings_list[0] if agent_findings_list else "No data"
    with col:
        st.markdown(
            f"""
            <div style="border:2px solid {color}; border-radius:8px; padding:12px;
                        background:{color}11; min-height:130px;">
                <b>{label}</b><br/>
                <span style="color:{color}; font-weight:bold; font-size:1.1rem;">
                    {status.upper()}
                </span>
                <br/>
                <small>Confidence: {confidence:.0%}</small><br/>
                <small style="color:#555;">{top_finding[:80]}</small>
            </div>
            """,
            unsafe_allow_html=True,
        )

# ---- Expanders ----
with st.expander("View Full Audit Trail"):
    st.json(result.get("audit", []))

with st.expander("View Agent Graph (Mermaid)"):
    st.code(MERMAID_GRAPH, language="text")
    st.caption("Paste the above into https://mermaid.live to render the graph.")

with st.expander("View Raw State"):
    st.json(state)
