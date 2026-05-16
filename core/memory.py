"""Shared pipeline memory store for inter-agent communication."""
from datetime import datetime
from typing import Any, Dict, List, Optional


class PipelineMemory:
    """Shared context store that agents read/write during pipeline execution."""

    def __init__(self) -> None:
        self._store: Dict[str, Any] = {}
        self._history: List[Dict[str, Any]] = []

    def write(self, agent: str, key: str, value: Any) -> None:
        full_key = f"{agent}:{key}"
        self._store[full_key] = value
        self._history.append({
            "agent": agent,
            "key": key,
            "value": value,
            "timestamp": datetime.now().isoformat(),
        })

    def read(self, agent: str, key: str) -> Optional[Any]:
        return self._store.get(f"{agent}:{key}")

    def read_any(self, key: str) -> Dict[str, Any]:
        """Read a key across all agents."""
        return {k: v for k, v in self._store.items() if k.endswith(f":{key}")}

    def get_history(self) -> List[Dict[str, Any]]:
        return self._history.copy()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "store": self._store.copy(),
            "history": self._history.copy(),
        }
