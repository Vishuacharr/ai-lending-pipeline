"""Per-agent audit logger for the mortgage pipeline."""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional


class AuditLogger:
    def __init__(self, loan_id: str) -> None:
        self.loan_id = loan_id
        self.entries: List[Dict[str, Any]] = []

    def log(
        self,
        agent_name: str,
        input_summary: str,
        decision: str,
        confidence: float,
        findings: List[str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        entry: Dict[str, Any] = {
            "loan_id": self.loan_id,
            "agent": agent_name,
            "timestamp": datetime.now().isoformat(),
            "input_summary": input_summary,
            "decision": decision,
            "confidence": confidence,
            "findings": findings,
            "metadata": metadata or {},
        }
        self.entries.append(entry)
        return entry

    def get_entries(self) -> List[Dict[str, Any]]:
        return self.entries.copy()

    def get_agent_entry(self, agent_name: str) -> Dict[str, Any]:
        for entry in self.entries:
            if entry["agent"] == agent_name:
                return entry
        return {}

    def to_json(self) -> str:
        return json.dumps(self.entries, indent=2)
