"""LangGraph state definition for the mortgage pipeline."""
from typing import TypedDict, Optional, List, Dict, Any


class AgentFinding(TypedDict):
    agent: str
    status: str        # "pass" | "flag" | "reject" | "skip"
    confidence: float
    findings: List[str]
    timestamp: str


class LoanState(TypedDict):
    loan_id: str
    application: Dict[str, Any]
    documents: List[Dict[str, Any]]
    classified_docs: Dict[str, str]           # doc_id -> doc_type
    agent_findings: Dict[str, AgentFinding]
    income_verified: Optional[bool]
    appraisal_clear: Optional[bool]
    trid_compliant: Optional[bool]
    cd_balanced: Optional[bool]
    final_decision: Optional[str]            # "APPROVED" | "REVIEW" | "REJECTED"
    decision_reasons: List[str]
    pipeline_status: str                     # "running" | "complete" | "halted"
    errors: List[str]
