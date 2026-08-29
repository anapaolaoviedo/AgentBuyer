import hashlib
import json
import threading
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from shared.schemas import AuditLogEntry, EventType, ActorType
from mandate.sign import canonical_json


class CryptographicAuditLedger:
    """
    Append-only SHA-256 hash-chained cryptographic ledger.
    Every event is cryptographically linked to the previous entry, providing tamper-evident proof
    for cardholders, merchants, and chargeback auditors.
    """

    GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000"

    def __init__(self):
        self._entries: List[AuditLogEntry] = []
        self._lock = threading.Lock()

    def _compute_hash(
        self,
        index: int,
        prev_hash: str,
        timestamp: str,
        event_type: str,
        actor_type: str,
        actor_id: str,
        mandate_id: Optional[str],
        attempt_id: Optional[str],
        details: Dict[str, Any],
    ) -> str:
        payload = {
            "index": index,
            "prev_hash": prev_hash,
            "timestamp": timestamp,
            "event_type": event_type,
            "actor_type": actor_type,
            "actor_id": actor_id,
            "mandate_id": mandate_id,
            "attempt_id": attempt_id,
            "details": details,
        }
        return hashlib.sha256(canonical_json(payload)).hexdigest()

    def append_entry(
        self,
        event_type: EventType | str,
        actor_type: ActorType | str,
        actor_id: str,
        details: Dict[str, Any],
        mandate_id: Optional[str] = None,
        attempt_id: Optional[str] = None,
        signature: Optional[str] = None,
    ) -> AuditLogEntry:
        with self._lock:
            index = len(self._entries)
            prev_hash = self._entries[-1].hash if self._entries else self.GENESIS_HASH
            timestamp = datetime.now(timezone.utc).isoformat()
            
            event_type_str = event_type.value if hasattr(event_type, "value") else str(event_type)
            actor_type_str = actor_type.value if hasattr(actor_type, "value") else str(actor_type)

            entry_hash = self._compute_hash(
                index=index,
                prev_hash=prev_hash,
                timestamp=timestamp,
                event_type=event_type_str,
                actor_type=actor_type_str,
                actor_id=actor_id,
                mandate_id=mandate_id,
                attempt_id=attempt_id,
                details=details,
            )

            entry = AuditLogEntry(
                entry_id=f"aud_{index:06d}_{entry_hash[:8]}",
                index=index,
                prev_hash=prev_hash,
                hash=entry_hash,
                timestamp=timestamp,
                event_type=event_type_str,
                actor_type=actor_type_str,
                actor_id=actor_id,
                mandate_id=mandate_id,
                attempt_id=attempt_id,
                details=details,
                signature=signature,
            )

            self._entries.append(entry)
            return entry

    def verify_chain_integrity(self) -> Tuple[bool, Optional[str]]:
        """
        Verifies the cryptographic integrity of the entire audit chain.
        Returns (is_valid: bool, error_description: Optional[str]).
        """
        with self._lock:
            expected_prev = self.GENESIS_HASH
            for i, entry in enumerate(self._entries):
                if entry.index != i:
                    return False, f"Index mismatch at position {i}: entry has index {entry.index}"
                if entry.prev_hash != expected_prev:
                    return False, f"Broken hash chain at index {i}: expected prev_hash {expected_prev}, found {entry.prev_hash}"
                
                calculated_hash = self._compute_hash(
                    index=entry.index,
                    prev_hash=entry.prev_hash,
                    timestamp=entry.timestamp,
                    event_type=entry.event_type,
                    actor_type=entry.actor_type,
                    actor_id=entry.actor_id,
                    mandate_id=entry.mandate_id,
                    attempt_id=entry.attempt_id,
                    details=entry.details,
                )
                if calculated_hash != entry.hash:
                    return False, f"Tampered entry at index {i}: calculated hash {calculated_hash} != stored {entry.hash}"

                expected_prev = entry.hash

            return True, "Chain integrity 100% verified (Zero tampering detected)."

    def get_all_entries(self) -> List[AuditLogEntry]:
        with self._lock:
            return [e.model_copy(deep=True) for e in self._entries]

    def get_trail_for(
        self,
        role: str = "auditor",
        mandate_id: Optional[str] = None,
        attempt_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Returns role-customized view of the audit ledger:
        - 'human': clean receipts, notifications, active status changes
        - 'merchant': compliance, verification results, settlement tokens
        - 'auditor': full cryptographic hash-chain, proofs, raw signatures
        """
        with self._lock:
            raw_entries = self._entries

        filtered = []
        for e in raw_entries:
            if mandate_id and e.mandate_id != mandate_id:
                continue
            if attempt_id and e.attempt_id != attempt_id:
                continue

            if role.lower() == "human":
                # High-level user friendly view
                filtered.append({
                    "time": e.timestamp,
                    "event": e.event_type,
                    "actor": f"{e.actor_type} ({e.actor_id})",
                    "mandate_id": e.mandate_id,
                    "summary": e.details.get("summary") or e.details.get("reason") or e.event_type,
                    "amount": e.details.get("amount"),
                    "status": e.details.get("status", "OK"),
                })
            elif role.lower() == "merchant":
                # Merchant compliance & verification view
                filtered.append({
                    "time": e.timestamp,
                    "event": e.event_type,
                    "actor_id": e.actor_id,
                    "attempt_id": e.attempt_id,
                    "mandate_id": e.mandate_id,
                    "authorized": e.details.get("authorized", False),
                    "settlement_id": e.details.get("settlement_id"),
                    "verification_checks": e.details.get("checks", {}),
                    "dispute_token": e.details.get("dispute_token"),
                })
            else:
                # Auditor full view (includes hashes and raw payloads)
                filtered.append(e.model_dump())

        return filtered

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


# Global singleton audit ledger
audit_ledger = CryptographicAuditLedger()
