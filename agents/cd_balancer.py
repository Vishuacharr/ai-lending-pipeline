"""CD Balancer agent — verifies Closing Disclosure mathematical balance."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.audit import AuditLogger
from core.memory import PipelineMemory
from core.state import AgentFinding, LoanState

AGENT_NAME = "cd_balancer"
MAX_DISCREPANCY = 0.50  # $0.50 tolerance


def balance_cd(
    state: LoanState,
    memory: PipelineMemory,
    audit: AuditLogger,
) -> LoanState:
    """
    Verify CD balance:
    cash_to_close = loan_amount - down_payment + total_closing_costs
                    - lender_credits - seller_credits
    """
    application = state["application"]
    classified_docs = state["classified_docs"]
    documents = state["documents"]

    loan_amount = float(application["loan_amount"])
    findings: List[str] = []
    status = "pass"
    confidence = 1.0

    # Find Closing Disclosure document
    cd_doc: Optional[Dict[str, Any]] = None
    doc_map = {d["doc_id"]: d for d in documents}
    for doc_id, doc_type in classified_docs.items():
        if doc_type == "CLOSING_DISCLOSURE":
            cd_doc = doc_map.get(doc_id)
            break

    if cd_doc is None:
        findings.append("No CLOSING_DISCLOSURE document found — skipping CD balance check")
        status = "pass"
        confidence = 0.5
    else:
        data = cd_doc.get("data", {})
        line_items: List[Dict[str, Any]] = data.get("line_items", [])
        down_payment = float(data.get("down_payment", 0.0))
        lender_credits = float(data.get("lender_credits", 0.0))
        seller_credits = float(data.get("seller_credits", 0.0))
        stated_cash_to_close = float(data.get("cash_to_close_stated", 0.0))

        # Sum all line items
        total_closing_costs = sum(float(item.get("amount", 0.0)) for item in line_items)
        line_detail = [
            f"  {item.get('line_number','?')} {item.get('description','?')}: ${float(item.get('amount',0)):.2f}"
            for item in line_items
        ]

        # Compute expected cash to close
        computed = (
            loan_amount
            - down_payment
            + total_closing_costs
            - lender_credits
            - seller_credits
        )
        discrepancy = abs(computed - stated_cash_to_close)

        findings.append(f"Loan amount: ${loan_amount:,.2f}")
        findings.append(f"Down payment: ${down_payment:,.2f}")
        findings.append(f"Total closing costs (from {len(line_items)} items): ${total_closing_costs:,.2f}")
        findings.extend(line_detail)
        findings.append(f"Lender credits: ${lender_credits:,.2f}")
        findings.append(f"Seller credits: ${seller_credits:,.2f}")
        findings.append(f"Computed cash to close: ${computed:,.2f}")
        findings.append(f"Stated cash to close:   ${stated_cash_to_close:,.2f}")
        findings.append(f"Discrepancy: ${discrepancy:.2f}")

        if discrepancy > MAX_DISCREPANCY:
            status = "reject"
            confidence = 0.1
            findings.append(
                f"REJECT: Discrepancy ${discrepancy:.2f} exceeds ${MAX_DISCREPANCY:.2f} tolerance"
            )
        else:
            findings.append(f"PASS: Balance within ${MAX_DISCREPANCY:.2f} tolerance")

        balance_result = {
            "passed": status == "pass",
            "discrepancy": round(discrepancy, 2),
            "computed": round(computed, 2),
            "stated": round(stated_cash_to_close, 2),
            "total_closing_costs": round(total_closing_costs, 2),
        }
        memory.write(AGENT_NAME, "balance_result", balance_result)

    state["cd_balanced"] = status == "pass"

    finding: AgentFinding = {
        "agent": AGENT_NAME,
        "status": status,
        "confidence": round(confidence, 2),
        "findings": findings,
        "timestamp": datetime.now().isoformat(),
    }
    state["agent_findings"][AGENT_NAME] = finding

    if status == "reject":
        state["decision_reasons"].append(
            f"CD balance REJECT: " + next(
                (f for f in reversed(findings) if "Discrepancy" in f or "REJECT" in f), ""
            )
        )

    audit.log(
        agent_name=AGENT_NAME,
        input_summary=f"CD balance check; loan_amount=${loan_amount:,.2f}",
        decision=status,
        confidence=round(confidence, 2),
        findings=findings,
        metadata=memory.read(AGENT_NAME, "balance_result") or {},
    )

    return state
