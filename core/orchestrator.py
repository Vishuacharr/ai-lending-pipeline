"""
LoanPipeline: LangGraph StateGraph with 5 agent nodes and conditional routing.

Graph flow:
  document_classifier
       |
  income_verifier --(flag/reject)--> human_review_node --> END
       | (pass)
  appraisal_analyzer --(reject)--> rejection_node --> END
       | (pass)
  trid_compliance --(flag)--> human_review_node --> END
       | (pass)
  cd_balancer --(reject)--> rejection_node --> END
       | (pass)
  approval_node --> END
"""
from typing import Any, Dict

from langgraph.graph import END, StateGraph

from agents.appraisal_analyzer import analyze_appraisal
from agents.cd_balancer import balance_cd
from agents.document_classifier import classify_documents
from agents.income_verifier import verify_income
from agents.trid_compliance import check_trid
from core.audit import AuditLogger
from core.memory import PipelineMemory
from core.state import LoanState

# Module-level instances (reset per run via LoanPipeline.run)
_memory: PipelineMemory = PipelineMemory()
_audit: AuditLogger = AuditLogger("init")


def get_memory() -> PipelineMemory:
    return _memory


def get_audit() -> AuditLogger:
    return _audit


# ---------------------------------------------------------------------------
# Node functions — each wraps an agent
# ---------------------------------------------------------------------------

def node_classify(state: LoanState) -> LoanState:
    return classify_documents(state, _memory, _audit)


def node_income(state: LoanState) -> LoanState:
    return verify_income(state, _memory, _audit)


def node_appraisal(state: LoanState) -> LoanState:
    return analyze_appraisal(state, _memory, _audit)


def node_trid(state: LoanState) -> LoanState:
    return check_trid(state, _memory, _audit)


def node_cd(state: LoanState) -> LoanState:
    return balance_cd(state, _memory, _audit)


def node_approve(state: LoanState) -> LoanState:
    state["final_decision"] = "APPROVED"
    state["pipeline_status"] = "complete"
    state["decision_reasons"].append("All agents passed. Loan cleared for closing.")
    return state


def node_review(state: LoanState) -> LoanState:
    state["final_decision"] = "REVIEW"
    state["pipeline_status"] = "complete"
    return state


def node_reject(state: LoanState) -> LoanState:
    state["final_decision"] = "REJECTED"
    state["pipeline_status"] = "complete"
    return state


# ---------------------------------------------------------------------------
# Conditional routing functions
# ---------------------------------------------------------------------------

def route_after_income(state: LoanState) -> str:
    finding = state["agent_findings"].get("income_verifier", {})
    if finding.get("status") in ("flag", "reject"):
        return "review"
    return "appraisal"


def route_after_appraisal(state: LoanState) -> str:
    finding = state["agent_findings"].get("appraisal_analyzer", {})
    if finding.get("status") == "reject":
        return "reject"
    return "trid"


def route_after_trid(state: LoanState) -> str:
    finding = state["agent_findings"].get("trid_compliance", {})
    if finding.get("status") in ("flag", "reject"):
        return "review"
    return "cd"


def route_after_cd(state: LoanState) -> str:
    finding = state["agent_findings"].get("cd_balancer", {})
    if finding.get("status") == "reject":
        return "reject"
    return "approve"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_graph() -> Any:
    graph: StateGraph = StateGraph(LoanState)

    graph.add_node("classify", node_classify)
    graph.add_node("income", node_income)
    graph.add_node("appraisal", node_appraisal)
    graph.add_node("trid", node_trid)
    graph.add_node("cd", node_cd)
    graph.add_node("approve", node_approve)
    graph.add_node("review", node_review)
    graph.add_node("reject", node_reject)

    graph.set_entry_point("classify")
    graph.add_edge("classify", "income")
    graph.add_conditional_edges(
        "income",
        route_after_income,
        {"review": "review", "appraisal": "appraisal"},
    )
    graph.add_conditional_edges(
        "appraisal",
        route_after_appraisal,
        {"reject": "reject", "trid": "trid"},
    )
    graph.add_conditional_edges(
        "trid",
        route_after_trid,
        {"review": "review", "cd": "cd"},
    )
    graph.add_conditional_edges(
        "cd",
        route_after_cd,
        {"reject": "reject", "approve": "approve"},
    )
    graph.add_edge("approve", END)
    graph.add_edge("review", END)
    graph.add_edge("reject", END)

    return graph.compile()


class LoanPipeline:
    def __init__(self) -> None:
        self.graph = build_graph()

    def run(
        self,
        loan_id: str,
        application: Dict[str, Any],
        documents: list,
    ) -> Dict[str, Any]:
        global _memory, _audit
        _memory = PipelineMemory()
        _audit = AuditLogger(loan_id)

        initial_state: LoanState = {
            "loan_id": loan_id,
            "application": application,
            "documents": documents,
            "classified_docs": {},
            "agent_findings": {},
            "income_verified": None,
            "appraisal_clear": None,
            "trid_compliant": None,
            "cd_balanced": None,
            "final_decision": None,
            "decision_reasons": [],
            "pipeline_status": "running",
            "errors": [],
        }

        final_state = self.graph.invoke(initial_state)
        return {
            "state": final_state,
            "audit": _audit.get_entries(),
            "memory": _memory.to_dict(),
        }
