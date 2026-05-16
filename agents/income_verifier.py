"""Income verifier agent — cross-checks income across W2, paystub, and tax return."""
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from core.audit import AuditLogger
from core.memory import PipelineMemory
from core.state import AgentFinding, LoanState

AGENT_NAME = "income_verifier"
FLAG_THRESHOLD = 0.05    # 5% variance triggers flag
REJECT_THRESHOLD = 0.15  # 15% variance triggers reject


def _annualize(amount: float, period: str) -> float:
    """Convert amount to annual based on period."""
    if period.upper() == "MONTHLY":
        return amount * 12
    return amount


def _extract_income_from_doc(doc: Dict[str, Any], doc_type: str) -> Optional[Tuple[float, str]]:
    """
    Returns (annual_income, label) or None if not applicable.
    """
    data = doc.get("data", {})
    try:
        if doc_type == "W2":
            wages = float(data["wages_tips_other_compensation"])
            return wages, "W2 wages"
        elif doc_type == "PAYSTUB":
            ytd_gross = float(data["ytd_gross"])
            current_month = int(data.get("current_month", 12))
            if current_month == 0:
                current_month = 12
            annualized = ytd_gross / (current_month / 12)
            return annualized, f"Paystub YTD annualized (month {current_month})"
        elif doc_type == "TAX_RETURN_1040":
            agi = float(data["adjusted_gross_income"])
            return agi, "Tax return AGI"
    except (KeyError, TypeError, ZeroDivisionError):
        return None
    return None


def verify_income(
    state: LoanState,
    memory: PipelineMemory,
    audit: AuditLogger,
) -> LoanState:
    """Verify stated income against all income documents."""
    application = state["application"]
    classified_docs = state["classified_docs"]
    documents = state["documents"]
    stated_income = float(application["borrower"]["annual_income_stated"])

    findings: List[str] = [f"Stated income: ${stated_income:,.2f}"]
    variances: List[float] = []
    income_sources: List[float] = []
    worst_status = "pass"
    confidence = 1.0

    # Index docs by id for easy lookup
    doc_map = {d["doc_id"]: d for d in documents}

    income_doc_types = {"W2", "PAYSTUB", "TAX_RETURN_1040"}

    for doc_id, doc_type in classified_docs.items():
        if doc_type not in income_doc_types:
            continue
        doc = doc_map.get(doc_id)
        if not doc:
            continue

        result = _extract_income_from_doc(doc, doc_type)
        if result is None:
            findings.append(f"{doc_id} ({doc_type}): could not extract income — skipping")
            continue

        doc_income, label = result
        variance = abs(doc_income - stated_income) / stated_income if stated_income > 0 else 0.0
        variances.append(variance)
        income_sources.append(doc_income)

        findings.append(
            f"{label}: ${doc_income:,.2f} — variance {variance:.1%}"
        )

        if variance > REJECT_THRESHOLD:
            worst_status = "reject"
            findings.append(f"  !! REJECT threshold exceeded ({variance:.1%} > {REJECT_THRESHOLD:.0%})")
            confidence = max(0.2, confidence - 0.4)
        elif variance > FLAG_THRESHOLD:
            if worst_status != "reject":
                worst_status = "flag"
            findings.append(f"  ! FLAG threshold exceeded ({variance:.1%} > {FLAG_THRESHOLD:.0%})")
            confidence = max(0.5, confidence - 0.2)

    if not variances:
        findings.append("No income documents found — skipping income check")
        worst_status = "pass"
        confidence = 0.5

    # Verified income = lowest figure found (conservative)
    verified_income = min(income_sources) if income_sources else stated_income
    memory.write(AGENT_NAME, "verified_income", verified_income)
    memory.write(AGENT_NAME, "max_variance", max(variances) if variances else 0.0)

    state["income_verified"] = worst_status == "pass"

    finding: AgentFinding = {
        "agent": AGENT_NAME,
        "status": worst_status,
        "confidence": round(confidence, 2),
        "findings": findings,
        "timestamp": datetime.now().isoformat(),
    }
    state["agent_findings"][AGENT_NAME] = finding

    if worst_status in ("flag", "reject"):
        state["decision_reasons"].append(
            f"Income verification {worst_status.upper()}: max variance "
            f"{max(variances):.1%} from stated income."
        )

    audit.log(
        agent_name=AGENT_NAME,
        input_summary=f"Stated income ${stated_income:,.2f}; {len(variances)} income docs checked",
        decision=worst_status,
        confidence=round(confidence, 2),
        findings=findings,
        metadata={
            "stated_income": stated_income,
            "verified_income": verified_income,
            "variances": [round(v, 4) for v in variances],
        },
    )

    return state
