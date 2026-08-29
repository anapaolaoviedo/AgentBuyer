import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from shared.schemas import Mandate, MandateStatus


class MandateStore:
    """
    Authoritative, thread-safe in-memory store for Mandates.
    CRITICAL RULE: NO CACHING. All status checks query this live registry directly.
    """

    def __init__(self):
        self._mandates: Dict[str, Mandate] = {}
        self._lock = threading.Lock()

    def save_mandate(self, mandate: Mandate) -> Mandate:
        with self._lock:
            self._mandates[mandate.mandate_id] = mandate.model_copy(deep=True)
            return self._mandates[mandate.mandate_id]

    def get_mandate(self, mandate_id: str) -> Optional[Mandate]:
        with self._lock:
            mandate = self._mandates.get(mandate_id)
            if not mandate:
                return None
            # Live evaluation of expiration
            m_copy = mandate.model_copy(deep=True)
            if m_copy.status == MandateStatus.ACTIVE:
                now = datetime.now(timezone.utc)
                exp = datetime.fromisoformat(m_copy.expires_at)
                if now > exp:
                    m_copy.status = MandateStatus.EXPIRED
                    self._mandates[mandate_id].status = MandateStatus.EXPIRED
            return m_copy

    def list_mandates(self, human_id: Optional[str] = None) -> List[Mandate]:
        with self._lock:
            mandates = []
            now = datetime.now(timezone.utc)
            for m in self._mandates.values():
                m_copy = m.model_copy(deep=True)
                if m_copy.status == MandateStatus.ACTIVE:
                    exp = datetime.fromisoformat(m_copy.expires_at)
                    if now > exp:
                        m_copy.status = MandateStatus.EXPIRED
                        m.status = MandateStatus.EXPIRED
                if human_id is None or m_copy.human_id == human_id:
                    mandates.append(m_copy)
            return mandates

    def revoke_mandate(self, mandate_id: str, reason: str = "Revoked by cardholder") -> bool:
        """
        Live Revocation (The Trial by Fire).
        Instantly updates status to REVOKED. Subsequent purchase verifications will fail immediately.
        """
        with self._lock:
            if mandate_id not in self._mandates:
                return False
            mandate = self._mandates[mandate_id]
            mandate.status = MandateStatus.REVOKED
            mandate.revoked_at = datetime.now(timezone.utc).isoformat()
            mandate.revocation_reason = reason
            return True

    def pause_mandate(self, mandate_id: str) -> bool:
        with self._lock:
            if mandate_id not in self._mandates:
                return False
            self._mandates[mandate_id].status = MandateStatus.PAUSED
            return True

    def resume_mandate(self, mandate_id: str) -> bool:
        with self._lock:
            if mandate_id not in self._mandates:
                return False
            self._mandates[mandate_id].status = MandateStatus.ACTIVE
            return True

    def get_live_status(self, mandate_id: str) -> Tuple[Optional[MandateStatus], Optional[str]]:
        mandate = self.get_mandate(mandate_id)
        if not mandate:
            return None, "Mandate not found"
        return mandate.status, mandate.revocation_reason

    def clear(self) -> None:
        with self._lock:
            self._mandates.clear()


# Global authoritative singleton store
mandate_store = MandateStore()
