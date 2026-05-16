"""Document classifier agent — classifies loan documents by type."""
from datetime import datetime
from typing import Dict, List

from core.audit import AuditLogger
from core.memory import PipelineMemory
from core.state import AgentFinding, LoanState

AGENT_NAME = "document_classifier"

# Filename keyword patterns for fallback classification
_FILENAME_PATTERNS: Dict[str, List[str]] = {
    "W2": ["w2", "w-2", "wage"],
    "PAYSTUB": ["paystub", "pay_stub", "paycheck", "earnings"],
    "TAX_RETURN_1040": ["1040", "tax_return", "taxreturn"],
    "APPRAISAL_REPORT": ["appraisal", "appraiser", "property_value"],
    "CLOSING_DISCLOSURE": ["closing_disclosure", "cd_final", "closing_disc"],
    "LOAN_ESTIMATE": ["loan_estimate", "le_initial", "loaneest"],
    "PURCHASE_CONTRACT": ["purchase_contract", "sales_contract", "purchase_agree"],
    "TITLE_COMMITMENT": ["title_commit", "title_ins", "title_report"],
}


def _infer_type_from_filename(filename: str) -> str:
    lower = filename.lower()
    for doc_type, patterns in _FILENAME_PATTERNS.items():
        for pat in patterns:
            if pat in lower:
                return doc_type
    return "UNKNOWN"


def classify_documents(
    state: LoanState,
    memory: PipelineMemory,
    audit: AuditLogger,
) -> LoanState:
    """Classify all documents in the loan package."""
    documents = state.get("documents", [])
    classified: Dict[str, str] = {}
    findings: List[str] = []

    for doc in documents:
        doc_id = doc.get("doc_id", "unknown")
        # Prefer explicit doc_type field; fall back to filename inference
        doc_type = doc.get("doc_type", "")
        if not doc_type or doc_type == "UNKNOWN":
            doc_type = _infer_type_from_filename(doc.get("filename", ""))

        classified[doc_id] = doc_type
        findings.append(f"{doc_id} -> {doc_type} ({doc.get('filename', 'no-filename')})")

    state["classified_docs"] = classified

    # Write to shared memory
    memory.write(AGENT_NAME, "doc_types", classified)
    memory.write(AGENT_NAME, "doc_count", len(classified))

    finding: AgentFinding = {
        "agent": AGENT_NAME,
        "status": "pass",
        "confidence": 1.0,
        "findings": findings,
        "timestamp": datetime.now().isoformat(),
    }
    state["agent_findings"][AGENT_NAME] = finding

    audit.log(
        agent_name=AGENT_NAME,
        input_summary=f"{len(documents)} documents submitted",
        decision="pass",
        confidence=1.0,
        findings=findings,
        metadata={"classified_docs": classified},
    )

    return state
