"""TRID compliance agent — checks disclosure timelines and fee tolerances."""
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from core.audit import AuditLogger
from core.memory import PipelineMemory
from core.state import AgentFinding, LoanState

AGENT_NAME = "trid_compliance"

LE_ISSUANCE_MAX_DAYS = 3
CD_RECEIPT_MIN_DAYS = 3

# Zero-tolerance fee keys in doc data
ZERO_TOLERANCE_KEYS = ["origination_fee", "discount_points", "transfer_tax"]
# 10% tolerance fee keys
TEN_PCT_KEYS = ["recording_fee", "appraisal_fee", "credit_report_fee", "flood_determination"]


def _parse_date(val: Any) -> Optional[date]:
    if val is None:
        return None
    if isinstance(val, date):
        return val
    try:
        return datetime.strptime(str(val), "%Y-%m-%d").date()
    except ValueError:
        return None


def _check_timeline(application: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Check LE and CD timing rules. Returns (passed, findings)."""
    findings: List[str] = []
    passed = True

    app_date = _parse_date(application.get("application_date"))
    le_date = _parse_date(application.get("le_issued_date"))
    cd_date = _parse_date(application.get("cd_received_date"))
    close_date = _parse_date(application.get("closing_date"))

    if app_date and le_date:
        le_days = (le_date - app_date).days
        ok = le_days <= LE_ISSUANCE_MAX_DAYS
        findings.append(
            f"LE issued {le_days} day(s) after application ({'PASS' if ok else 'FAIL — must be <=3'})"
        )
        if not ok:
            passed = False
    else:
        findings.append("LE issuance date missing — cannot verify timeline")

    if cd_date and close_date:
        cd_days = (close_date - cd_date).days
        ok = cd_days >= CD_RECEIPT_MIN_DAYS
        findings.append(
            f"CD received {cd_days} day(s) before closing ({'PASS' if ok else 'FAIL — must be >=3'})"
        )
        if not ok:
            passed = False
    else:
        findings.append("CD receipt date missing — cannot verify timeline")

    return passed, findings


def _get_fee_amounts(
    doc: Optional[Dict[str, Any]], keys: List[str]
) -> Dict[str, float]:
    if doc is None:
        return {}
    data = doc.get("data", {})
    fees = data.get("fees", {})
    return {k: float(fees.get(k, 0.0)) for k in keys}


def _check_tolerances(
    le_doc: Optional[Dict[str, Any]],
    cd_doc: Optional[Dict[str, Any]],
) -> Tuple[str, List[str], Dict[str, Any]]:
    """
    Returns (status, findings, tolerance_results).
    status: "pass" | "flag" | "reject"
    """
    findings: List[str] = []
    status = "pass"
    tolerance_results: Dict[str, Any] = {}

    if le_doc is None or cd_doc is None:
        findings.append("LE or CD document missing — cannot check tolerances")
        return "pass", findings, tolerance_results

    # Zero-tolerance check
    le_zero = _get_fee_amounts(le_doc, ZERO_TOLERANCE_KEYS)
    cd_zero = _get_fee_amounts(cd_doc, ZERO_TOLERANCE_KEYS)
    zero_issues = []
    for key in ZERO_TOLERANCE_KEYS:
        le_val = le_zero.get(key, 0.0)
        cd_val = cd_zero.get(key, 0.0)
        if cd_val > le_val + 0.01:  # any increase
            zero_issues.append(f"{key}: LE=${le_val:.2f} -> CD=${cd_val:.2f} (+${cd_val - le_val:.2f})")
    if zero_issues:
        status = "reject"
        findings.append("REJECT: Zero-tolerance fee increases detected:")
        findings.extend([f"  {i}" for i in zero_issues])
    else:
        findings.append("Zero-tolerance bucket: PASS (no fee increases)")

    tolerance_results["zero_tolerance"] = {"issues": zero_issues, "passed": len(zero_issues) == 0}

    # 10% tolerance check
    le_ten = _get_fee_amounts(le_doc, TEN_PCT_KEYS)
    cd_ten = _get_fee_amounts(cd_doc, TEN_PCT_KEYS)
    le_sum = sum(le_ten.values())
    cd_sum = sum(cd_ten.values())
    if le_sum > 0:
        pct_increase = (cd_sum - le_sum) / le_sum * 100
        ok = pct_increase <= 10.0
        findings.append(
            f"10% bucket: LE total=${le_sum:.2f}, CD total=${cd_sum:.2f}, "
            f"increase={pct_increase:.1f}% ({'PASS' if ok else 'FAIL'})"
        )
        if not ok and status != "reject":
            status = "flag"
        tolerance_results["ten_percent"] = {
            "le_sum": le_sum,
            "cd_sum": cd_sum,
            "pct_increase": round(pct_increase, 2),
            "passed": ok,
        }
    else:
        findings.append("10% bucket: no LE fees found — skipping")

    return status, findings, tolerance_results


def check_trid(
    state: LoanState,
    memory: PipelineMemory,
    audit: AuditLogger,
) -> LoanState:
    """Check TRID timeline and fee tolerance compliance."""
    application = state["application"]
    classified_docs = state["classified_docs"]
    documents = state["documents"]

    doc_map = {d["doc_id"]: d for d in documents}
    le_doc: Optional[Dict[str, Any]] = None
    cd_doc: Optional[Dict[str, Any]] = None

    for doc_id, doc_type in classified_docs.items():
        if doc_type == "LOAN_ESTIMATE":
            le_doc = doc_map.get(doc_id)
        elif doc_type == "CLOSING_DISCLOSURE":
            cd_doc = doc_map.get(doc_id)

    all_findings: List[str] = []

    # Timeline check
    timeline_ok, timeline_findings = _check_timeline(application)
    all_findings.extend(timeline_findings)

    # Tolerance check
    tol_status, tol_findings, tol_results = _check_tolerances(le_doc, cd_doc)
    all_findings.extend(tol_findings)

    # Combine status
    if tol_status == "reject" or not timeline_ok:
        if tol_status == "reject":
            status = "reject"
        else:
            status = "flag"
    elif tol_status == "flag":
        status = "flag"
    else:
        status = "pass"

    confidence = 1.0 if status == "pass" else (0.4 if status == "reject" else 0.6)

    memory.write(AGENT_NAME, "tolerance_results", tol_results)
    memory.write(AGENT_NAME, "timeline_ok", timeline_ok)

    state["trid_compliant"] = status == "pass"

    finding: AgentFinding = {
        "agent": AGENT_NAME,
        "status": status,
        "confidence": confidence,
        "findings": all_findings,
        "timestamp": datetime.now().isoformat(),
    }
    state["agent_findings"][AGENT_NAME] = finding

    if status in ("flag", "reject"):
        state["decision_reasons"].append(
            f"TRID compliance {status.upper()}: " + "; ".join(all_findings[:3])
        )

    audit.log(
        agent_name=AGENT_NAME,
        input_summary="TRID timeline + fee tolerance check",
        decision=status,
        confidence=confidence,
        findings=all_findings,
        metadata={"tolerance_results": tol_results, "timeline_ok": timeline_ok},
    )

    return state
