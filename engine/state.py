from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Set, Optional
import threading


@dataclass
class MandateRollingState:
    mandate_id: str
    spent_this_month: float = 0.0
    count_this_month: int = 0
    used_nonces: Set[str] = field(default_factory=set)
    last_attempt_at: Optional[str] = None
    last_settled_at: Optional[str] = None


class MandateStateManager:
    """
    Thread-safe manager for rolling counters, budget depletion, and replay-protection nonces.
    """

    def __init__(self):
        self._states: Dict[str, MandateRollingState] = {}
        self._lock = threading.Lock()

    def get_state(self, mandate_id: str) -> MandateRollingState:
        with self._lock:
            if mandate_id not in self._states:
                self._states[mandate_id] = MandateRollingState(mandate_id=mandate_id)
            return self._states[mandate_id]

    def is_nonce_used(self, mandate_id: str, nonce: str) -> bool:
        with self._lock:
            if mandate_id not in self._states:
                return False
            return nonce in self._states[mandate_id].used_nonces

    def record_attempt(self, mandate_id: str, nonce: str) -> None:
        with self._lock:
            state = self.get_state(mandate_id)
            state.used_nonces.add(nonce)
            state.last_attempt_at = datetime.now(timezone.utc).isoformat()

    def record_successful_purchase(self, mandate_id: str, amount: float) -> None:
        with self._lock:
            state = self.get_state(mandate_id)
            state.spent_this_month += amount
            state.count_this_month += 1
            state.last_settled_at = datetime.now(timezone.utc).isoformat()

    def reset_state(self, mandate_id: str) -> None:
        with self._lock:
            self._states[mandate_id] = MandateRollingState(mandate_id=mandate_id)


# Global singleton instance
state_manager = MandateStateManager()
