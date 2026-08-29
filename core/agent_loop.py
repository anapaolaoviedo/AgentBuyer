import uuid
import secrets
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple, List
from numbers import Real
from copy import deepcopy

from shared.schemas import (
    Mandate,
    CatalogItem,
    PurchaseAttempt,
    VerificationResult,
    EventType,
    ActorType,
)
from mandate.sign import sign_payload
from core.merchant import vuelaya_merchant, VuelaYaMerchant, get_flights
from core.mandate_store import VERIFICATION_EVENTS, get_mandate
from audit.log import audit_ledger


class PurchasingAgent:
    """
    Autonomous purchasing agent that discovers deals, evaluates them against active mandates,
    signs purchase attempts cryptographically, and submits them to merchants.
    """

    def __init__(self, agent_id: str, agent_privkey: str, agent_pubkey: str):
        self.agent_id = agent_id
        self.agent_privkey = agent_privkey
        self.agent_pubkey = agent_pubkey
        self.purchase_history: List[Dict[str, Any]] = []

    def create_signed_attempt(
        self,
        mandate: Mandate,
        item: CatalogItem,
        merchant_id: str,
        override_amount: Optional[float] = None,
        tampered_nonce: Optional[str] = None,
        tampered_agent_id: Optional[str] = None,
        forge_signature: bool = False,
    ) -> PurchaseAttempt:
        attempt_id = f"att_{uuid.uuid4().hex[:10]}"
        timestamp = datetime.now(timezone.utc).isoformat()
        nonce = tampered_nonce if tampered_nonce else secrets.token_hex(16)
        active_agent_id = tampered_agent_id if tampered_agent_id else self.agent_id
        amount = override_amount if override_amount is not None else item.price

        unsigned_dict: Dict[str, Any] = {
            "attempt_id": attempt_id,
            "mandate_id": mandate.mandate_id,
            "agent_id": active_agent_id,
            "merchant_id": merchant_id,
            "item_id": item.item_id,
            "item_title": item.title,
            "category": item.category,
            "amount": amount,
            "currency": item.currency,
            "metadata": item.metadata,
            "timestamp": timestamp,
            "nonce": nonce,
        }

        if forge_signature:
            signature = "deadbeef" * 8
        else:
            signature = sign_payload(self.agent_privkey, unsigned_dict)

        return PurchaseAttempt(
            attempt_id=attempt_id,
            mandate_id=mandate.mandate_id,
            agent_id=active_agent_id,
            merchant_id=merchant_id,
            item_id=item.item_id,
            item_title=item.title,
            category=item.category,
            amount=amount,
            currency=item.currency,
            metadata=item.metadata,
            timestamp=timestamp,
            nonce=nonce,
            agent_signature=signature,
        )

    def attempt_purchase(
        self,
        mandate: Mandate,
        item: CatalogItem,
        merchant: Optional[VuelaYaMerchant] = None,
        override_amount: Optional[float] = None,
        tampered_nonce: Optional[str] = None,
        tampered_agent_id: Optional[str] = None,
        forge_signature: bool = False,
    ) -> Tuple[PurchaseAttempt, VerificationResult]:
        if merchant is None:
            merchant = vuelaya_merchant

        attempt = self.create_signed_attempt(
            mandate=mandate,
            item=item,
            merchant_id=merchant.MERCHANT_ID,
            override_amount=override_amount,
            tampered_nonce=tampered_nonce,
            tampered_agent_id=tampered_agent_id,
            forge_signature=forge_signature,
        )

        audit_ledger.append_entry(
            event_type=EventType.PURCHASE_ATTEMPTED,
            actor_type=ActorType.AGENT,
            actor_id=self.agent_id,
            mandate_id=mandate.mandate_id,
            attempt_id=attempt.attempt_id,
            details={
                "item_id": item.item_id,
                "title": item.title,
                "amount": attempt.amount,
                "category": item.category,
                "merchant": merchant.MERCHANT_ID,
            },
            signature=attempt.agent_signature,
        )

        verification_result = merchant.process_purchase(attempt)

        record = {
            "attempt_id": attempt.attempt_id,
            "mandate_id": mandate.mandate_id,
            "item_title": item.title,
            "amount": attempt.amount,
            "authorized": verification_result.authorized,
            "status": verification_result.status.value,
            "reason": verification_result.reason,
            "timestamp": attempt.timestamp,
        }
        self.purchase_history.append(record)

        return attempt, verification_result


def _price_limit(mandate: dict) -> int | float | None:
    """Lee price_below o max_amount con compatibilidad de contratos."""
    constraints = mandate.get("constraints", {}) or mandate.get("scope", {})
    conditions = constraints.get("conditions", []) if isinstance(constraints, dict) else []
    for condition in conditions:
        if isinstance(condition, dict) and condition.get("type") == "price_below":
            candidate = condition.get("value")
            if isinstance(candidate, Real) and not isinstance(candidate, bool):
                return candidate

    candidates = [
        mandate.get("price_below"),
        mandate.get("max_amount_per_purchase"),
        constraints.get("price_below") if isinstance(constraints, dict) else None,
        constraints.get("max_amount_per_purchase") if isinstance(constraints, dict) else None,
        constraints.get("max_amount_per_tx") if isinstance(constraints, dict) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, Real) and not isinstance(candidate, bool):
            return candidate
    return None


def run_agent(mandate_id: str) -> dict:
    """Descubre, decide, intenta y registra el resultado de una compra."""
    flights_seen = get_flights()
    record = get_mandate(mandate_id)
    mandate = record["mandate"] if record is not None else {}
    limit = _price_limit(mandate)

    eligible = [flight for flight in flights_seen if limit is not None and flight["price"] <= limit]
    selected_flight = min(eligible or flights_seen, key=lambda flight: flight["price"])
    attempt_id = f"att_agent_{uuid.uuid4().hex[:12]}"
    agent_id = mandate.get("agent", {}).get("id", "agent_marta")
    
    attempt = {
        "attempt_id": attempt_id,
        "mandate_id": mandate_id,
        "presented_by_agent": agent_id,
        "purchase": {
            "merchant_id": selected_flight["merchant_id"],
            "category": selected_flight["category"],
            "amount": selected_flight["price"],
            "currency": "USD",
            "description": f"Vuelo {selected_flight['route']}",
            "metadata": {"flight_id": selected_flight["id"], "price": selected_flight["price"]},
        },
    }

    from api.verify import verify_purchase as api_verify_purchase
    verification = api_verify_purchase(attempt)
    verdict = verification.get("verdict", "REJECT")
    completed = verdict == "APPROVE"

    VERIFICATION_EVENTS.append(
        {
            "mandate_id": mandate_id,
            "attempt_id": attempt_id,
            "verdict": verdict,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "agent_run",
        }
    )

    story = (
        f"Encontró {len(flights_seen)} vuelos. "
        + (f"Aplicó el límite price_below de {limit} USD y " if limit is not None else "No encontró un límite price_below utilizable y ")
        + f"eligió {selected_flight['id']} ({selected_flight['route']}) por {selected_flight['price']} USD. "
        + ("La compra fue completada tras recibir APPROVE." if completed else f"La compra no procedió: verify devolvió {verdict}. {verification.get('human_readable', '')}")
    )
    return {
        "mandate_id": mandate_id,
        "attempt_id": attempt_id,
        "flights_seen": flights_seen,
        "selected_flight": selected_flight,
        "selection_reason": "Vuelo más barato dentro de price_below." if eligible else "No hubo vuelo dentro de price_below; se intentó el más barato disponible.",
        "attempt": attempt,
        "verification": verification,
        "purchase_completed": completed,
        "human_readable": story,
    }
