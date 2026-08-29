import threading
from copy import deepcopy
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Union, Any

from shared.schemas import Mandate, MandateStatus

# Estado global autoritativo en memoria (Zero-Caching)
MANDATES: Dict[str, dict] = {}
VERIFICATION_EVENTS: List[dict] = []


class MandateStore:
    """
    Authoritative, thread-safe in-memory store for Mandates.
    CRITICAL RULE: NO CACHING. All status checks query this live registry directly.
    """

    def __init__(self):
        self._lock = threading.Lock()

    def save_mandate(self, mandate: Union[Mandate, dict]) -> Mandate:
        with self._lock:
            if isinstance(mandate, dict):
                m_obj = Mandate(**mandate)
            else:
                m_obj = mandate.model_copy(deep=True)

            mandate_id = m_obj.mandate_id
            MANDATES[mandate_id] = {
                "mandate": m_obj.model_dump(),
                "live_state": {
                    "status": m_obj.status.value.lower(),
                    "uses_count": 0,
                    "amount_spent": 0.0,
                    "revoked_at": m_obj.revoked_at,
                },
            }
            return m_obj

    def get_mandate(self, mandate_id: str) -> Optional[Mandate]:
        with self._lock:
            record = MANDATES.get(mandate_id)
            if not record:
                return None
            m_dict = record["mandate"]
            m_obj = Mandate(**m_dict)
            
            # Chequeo en vivo de expiración
            if m_obj.status == MandateStatus.ACTIVE:
                now = datetime.now(timezone.utc)
                exp = datetime.fromisoformat(m_obj.expires_at.replace("Z", "+00:00"))
                if now > exp:
                    m_obj.status = MandateStatus.EXPIRED
                    record["live_state"]["status"] = "expired"
                    record["mandate"]["status"] = "EXPIRED"

            if record["live_state"]["status"] == "revoked":
                m_obj.status = MandateStatus.REVOKED
                m_obj.revoked_at = record["live_state"].get("revoked_at")

            return m_obj

    def list_mandates(self, human_id: Optional[str] = None) -> List[Mandate]:
        with self._lock:
            mandates = []
            for m_id in list(MANDATES.keys()):
                m = self.get_mandate(m_id)
                if m and (human_id is None or m.human_id == human_id):
                    mandates.append(m)
            return mandates

    def revoke_mandate(self, mandate_id: str, reason: str = "Revoked by cardholder") -> bool:
        """Live Revocation Kill Switch."""
        with self._lock:
            record = MANDATES.get(mandate_id)
            if not record:
                return False
            record["live_state"]["status"] = "revoked"
            now_iso = datetime.now(timezone.utc).isoformat()
            record["live_state"]["revoked_at"] = now_iso
            record["mandate"]["status"] = "REVOKED"
            record["mandate"]["revoked_at"] = now_iso
            record["mandate"]["revocation_reason"] = reason
            return True

    def pause_mandate(self, mandate_id: str) -> bool:
        with self._lock:
            record = MANDATES.get(mandate_id)
            if not record:
                return False
            record["live_state"]["status"] = "paused"
            record["mandate"]["status"] = "PAUSED"
            return True

    def resume_mandate(self, mandate_id: str) -> bool:
        with self._lock:
            record = MANDATES.get(mandate_id)
            if not record:
                return False
            record["live_state"]["status"] = "active"
            record["mandate"]["status"] = "ACTIVE"
            return True

    def get_live_status(self, mandate_id: str) -> Tuple[Optional[MandateStatus], Optional[str]]:
        m = self.get_mandate(mandate_id)
        if not m:
            return None, "Mandate not found"
        return m.status, m.revocation_reason

    def clear(self) -> None:
        with self._lock:
            MANDATES.clear()
            VERIFICATION_EVENTS.clear()


# Global singleton instance
mandate_store = MandateStore()


# Funciones de compatibilidad funcional para API routes
def create_mandate(mandate: dict) -> dict:
    mandate_id = mandate.get("mandate_id")
    if not mandate_id:
        raise ValueError("El mandate_id es obligatorio")
    if mandate_id in MANDATES:
        raise ValueError("El mandate_id ya existe")

    MANDATES[mandate_id] = {
        "mandate": deepcopy(mandate),
        "live_state": {
            "status": "active",
            "uses_count": 0,
            "amount_spent": 0,
            "revoked_at": None,
        },
    }
    return get_mandate(mandate_id)


def get_mandate(mandate_id: str) -> dict | None:
    record = MANDATES.get(mandate_id)
    return deepcopy(record) if record is not None else None


def revoke_mandate(mandate_id: str) -> dict | None:
    record = MANDATES.get(mandate_id)
    if record is None:
        return None
    live_state = record["live_state"]
    if live_state["status"] != "revoked":
        live_state["status"] = "revoked"
        live_state["revoked_at"] = datetime.now(timezone.utc).isoformat()
    return get_mandate(mandate_id)


def apply_approved_purchase(mandate_id: str, amount: int | float) -> dict | None:
    record = MANDATES.get(mandate_id)
    if record is None:
        return None
    record["live_state"]["uses_count"] += 1
    record["live_state"]["amount_spent"] += amount
    return get_mandate(mandate_id)


def record_verification_event(
    mandate_id: str, attempt_id: str, verdict: str, timestamp: str
) -> None:
    VERIFICATION_EVENTS.append(
        {
            "mandate_id": mandate_id,
            "attempt_id": attempt_id,
            "verdict": verdict,
            "timestamp": timestamp,
        }
    )
