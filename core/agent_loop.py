import uuid
import secrets
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple, List

from shared.schemas import (
    Mandate,
    CatalogItem,
    PurchaseAttempt,
    VerificationResult,
    EventType,
    ActorType,
)
from mandate.sign import sign_payload
from core.merchant import vuelaya_merchant, VuelaYaMerchant
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
        """
        Constructs and cryptographically signs a purchase attempt.
        Supports security testing parameters to simulate rogue/tampered attempts.
        """
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
        """
        Executes the full purchase cycle: generate signed attempt -> send to merchant -> record receipt.
        """
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
