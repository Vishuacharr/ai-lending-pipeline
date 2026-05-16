"""Tests for all 3 sample loan packages."""
import json
import sys
from pathlib import Path

import pytest

# Ensure project root is on path when running directly
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.orchestrator import LoanPipeline  # noqa: E402

DATA_DIR = ROOT / "mortgage_data" / "sample_loans"


def load_loan(filename: str) -> dict:
    with open(DATA_DIR / filename) as f:
        return json.load(f)


def test_loan_001_clean_approves():
    """Clean loan should be auto-approved."""
    pipeline = LoanPipeline()
    loan = load_loan("loan_001_clean.json")
    result = pipeline.run(loan["loan_id"], loan["application"], loan["documents"])
    assert result["state"]["final_decision"] == "APPROVED", (
        f"Expected APPROVED, got {result['state']['final_decision']}. "
        f"Reasons: {result['state']['decision_reasons']}"
    )


def test_loan_002_income_mismatch_flags():
    """Income mismatch should route to REVIEW."""
    pipeline = LoanPipeline()
    loan = load_loan("loan_002_income_mismatch.json")
    result = pipeline.run(loan["loan_id"], loan["application"], loan["documents"])
    assert result["state"]["final_decision"] == "REVIEW", (
        f"Expected REVIEW, got {result['state']['final_decision']}. "
        f"Reasons: {result['state']['decision_reasons']}"
    )
    findings = result["state"]["agent_findings"]["income_verifier"]
    assert findings["status"] in ("flag", "reject"), (
        f"Expected income_verifier status flag/reject, got {findings['status']}"
    )


def test_loan_003_cd_imbalance_rejects():
    """CD imbalance should cause REJECTION."""
    pipeline = LoanPipeline()
    loan = load_loan("loan_003_cd_imbalance.json")
    result = pipeline.run(loan["loan_id"], loan["application"], loan["documents"])
    assert result["state"]["final_decision"] == "REJECTED", (
        f"Expected REJECTED, got {result['state']['final_decision']}. "
        f"Reasons: {result['state']['decision_reasons']}"
    )
    findings = result["state"]["agent_findings"]["cd_balancer"]
    assert findings["status"] == "reject", (
        f"Expected cd_balancer status reject, got {findings['status']}"
    )


def test_audit_trail_populated():
    """All processed agents should appear in audit trail."""
    pipeline = LoanPipeline()
    loan = load_loan("loan_001_clean.json")
    result = pipeline.run(loan["loan_id"], loan["application"], loan["documents"])
    agents_logged = [e["agent"] for e in result["audit"]]
    assert "document_classifier" in agents_logged
    assert "income_verifier" in agents_logged
    assert "cd_balancer" in agents_logged


def test_memory_populated():
    """Shared memory should contain agent outputs after pipeline run."""
    pipeline = LoanPipeline()
    loan = load_loan("loan_001_clean.json")
    result = pipeline.run(loan["loan_id"], loan["application"], loan["documents"])
    memory_store = result["memory"]["store"]
    assert "income_verifier:verified_income" in memory_store
    assert "appraisal_analyzer:ltv" in memory_store
    assert "cd_balancer:balance_result" in memory_store


def test_loan_001_ltv_under_80():
    """Loan 001 LTV should be under 80% (no PMI required)."""
    pipeline = LoanPipeline()
    loan = load_loan("loan_001_clean.json")
    result = pipeline.run(loan["loan_id"], loan["application"], loan["documents"])
    ltv = result["memory"]["store"].get("appraisal_analyzer:ltv", 1.0)
    assert ltv < 0.80, f"Expected LTV < 0.80, got {ltv}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
