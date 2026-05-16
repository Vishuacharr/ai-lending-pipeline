"""Appraisal analyzer agent — validates appraisal against purchase price and LTV limits."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.audit import AuditLogger
from core.memory import PipelineMemory
from core.state import AgentFinding, LoanState

AGENT_NAME = "appraisal_analyzer"

LTV_REJECT_THRESHOLD = 0.97
LTV_PMI_THRESHOLD = 0.80
COMP_VARIANCE_THRESHOLD = 0.20  # 20% comp variance triggers flag


def _check_comparables(
    comparable_sales: List[Dict[str, Any]],
    appraised_value: float,
) -> List[str]:
    """Check comparable sales for outliers vs appraised value."""
    issues: List[str] = []
    for comp in comparable_sales:
        comp_value = float(comp.get("sale_price", 0))
        if comp_value <= 0:
            continue
        comp_variance = abs(comp_value - appraised_value) / appraised_value
        addr = comp.get("address", "unknown")
        if comp_variance > COMP_VARIANCE_THRESHOLD:
            issues.append(
                f"Comp {addr}: ${comp_value:,.0f} is {comp_variance:.1%} from appraised value"
            )
    return issues


def analyze_appraisal(
    state: LoanState,
    memory: PipelineMemory,
    audit: AuditLogger,
) -> LoanState:
    """Analyze appraisal report against purchase price, loan amount, and comps."""
    application = state["application"]
    classified_docs = state["classified_docs"]
    documents = state["documents"]

    purchase_price = float(application["property"]["purchase_price"])
    loan_amount = float(application["loan_amount"])
    findings: List[str] = []
    status = "pass"
    confidence = 1.0

    # Find appraisal report
    appraisal_doc: Optional[Dict[str, Any]] = None
    doc_map = {d["doc_id"]: d for d in documents}
    for doc_id, doc_type in classified_docs.items():
        if doc_type == "APPRAISAL_REPORT":
            appraisal_doc = doc_map.get(doc_id)
            break

    if appraisal_doc is None:
        findings.append("No APPRAISAL_REPORT document found — skipping appraisal check")
        status = "pass"
        confidence = 0.5
    else:
        data = appraisal_doc.get("data", {})
        appraised_value = float(data.get("appraised_value", 0))
        comparable_sales = data.get("comparable_sales", [])

        ltv = loan_amount / appraised_value if appraised_value > 0 else 999.0
        findings.append(f"Appraised value: ${appraised_value:,.2f}")
        findings.append(f"Purchase price: ${purchase_price:,.2f}")
        findings.append(f"Loan amount: ${loan_amount:,.2f}")
        findings.append(f"LTV: {ltv:.2%}")

        # Check appraisal gap
        if appraised_value < purchase_price:
            gap = purchase_price - appraised_value
            findings.append(f"WARNING: Appraisal gap of ${gap:,.2f} (appraised < purchase price)")
            status = "flag"
            confidence -= 0.2

        # LTV checks
        if ltv > LTV_REJECT_THRESHOLD:
            findings.append(f"REJECT: LTV {ltv:.2%} exceeds maximum {LTV_REJECT_THRESHOLD:.0%}")
            status = "reject"
            confidence = 0.1
        elif ltv > LTV_PMI_THRESHOLD:
            findings.append(f"FLAG: LTV {ltv:.2%} > {LTV_PMI_THRESHOLD:.0%} — PMI required")
            if status != "reject":
                status = "flag"
            confidence -= 0.1

        # Comparable sales check
        comp_issues = _check_comparables(comparable_sales, appraised_value)
        if comp_issues:
            findings.extend(comp_issues)
            findings.append(f"FLAG: {len(comp_issues)} comparable(s) outside 20% variance")
            if status not in ("reject",):
                status = "flag"
            confidence -= 0.1
        else:
            findings.append(f"Comparables check passed ({len(comparable_sales)} comps reviewed)")

        memory.write(AGENT_NAME, "ltv", round(ltv, 4))
        memory.write(AGENT_NAME, "appraised_value", appraised_value)

    confidence = max(0.0, round(confidence, 2))
    state["appraisal_clear"] = status == "pass"

    finding: AgentFinding = {
        "agent": AGENT_NAME,
        "status": status,
        "confidence": confidence,
        "findings": findings,
        "timestamp": datetime.now().isoformat(),
    }
    state["agent_findings"][AGENT_NAME] = finding

    if status in ("flag", "reject"):
        state["decision_reasons"].append(
            f"Appraisal {status.upper()}: " + "; ".join(findings[-3:])
        )

    audit.log(
        agent_name=AGENT_NAME,
        input_summary=f"Purchase ${purchase_price:,.0f}, Loan ${loan_amount:,.0f}",
        decision=status,
        confidence=confidence,
        findings=findings,
        metadata={
            "purchase_price": purchase_price,
            "loan_amount": loan_amount,
            "ltv": memory.read(AGENT_NAME, "ltv"),
        },
    )

    return state
