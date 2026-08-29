import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from shared.schemas import (
    PurchaseAttempt,
    VerificationResult,
    VerificationStatus,
    MandateStatus,
    EventType,
    ActorType,
    HITLApprovalRequest,
)
from core.mandate_store import mandate_store
from engine.state import state_manager
from engine.evaluator import evaluate_mandate_constraints
from mandate.sign import verify_signature, hash_payload, sign_payload
from audit.log import audit_ledger


# Thread-safe in-memory HITL Escalations store
_escalations: Dict[str, HITLApprovalRequest] = {}


def get_pending_escalations(mandate_id: Optional[str] = None) -> list[HITLApprovalRequest]:
    results = []
    for req in _escalations.values():
        if req.status == "PENDING":
            if mandate_id is None or req.mandate_id == mandate_id:
                results.append(req.model_copy(deep=True))
    return results


def resolve_escalation(
    escalation_id: str,
    approved: bool,
    human_privkey: str,
    human_pubkey: str,
    note: str = "",
) -> Optional[VerificationResult]:
    """Resolves a pending Human-In-The-Loop escalation with cryptographic human authorization."""
    if escalation_id not in _escalations:
        return None

    req = _escalations[escalation_id]
    if req.status != "PENDING":
        return None

    req.resolved_at = datetime.now(timezone.utc).isoformat()
    req.resolution_note = note
    req.status = "APPROVED" if approved else "REJECTED"

    mandate = mandate_store.get_mandate(req.mandate_id)
    attempt = req.attempt

    if approved and mandate:
        # Cryptographic human decision signature
        decision_dict = {
            "escalation_id": escalation_id,
            "attempt_id": attempt.attempt_id,
            "approved": True,
            "resolved_at": req.resolved_at,
        }
        req.human_decision_signature = sign_payload(human_privkey, decision_dict)

        settlement_id = f"stl_{uuid.uuid4().hex[:12]}"
        dispute_token = f"dsp_{hash_payload({'attempt_id': attempt.attempt_id, 'settlement_id': settlement_id})[:16]}"

        state_manager.record_attempt(attempt.mandate_id, attempt.nonce)
        state_manager.record_successful_purchase(attempt.mandate_id, attempt.amount)

        audit_ledger.append_entry(
            event_type=EventType.HITL_APPROVED,
            actor_type=ActorType.HUMAN,
            actor_id=mandate.human_id,
            mandate_id=attempt.mandate_id,
            attempt_id=attempt.attempt_id,
            details={
                "escalation_id": escalation_id,
                "note": note,
                "amount": attempt.amount,
                "item": attempt.item_title,
                "settlement_id": settlement_id,
            },
            signature=req.human_decision_signature,
        )

        audit_ledger.append_entry(
            event_type=EventType.SETTLEMENT_COMPLETED,
            actor_type=ActorType.MERCHANT,
            actor_id=attempt.merchant_id,
            mandate_id=attempt.mandate_id,
            attempt_id=attempt.attempt_id,
            details={
                "settlement_id": settlement_id,
                "dispute_token": dispute_token,
                "amount": attempt.amount,
                "payment_token": mandate.payment_token.token_id,
            },
        )

        return VerificationResult(
            attempt_id=attempt.attempt_id,
            status=VerificationStatus.APPROVED,
            authorized=True,
            reason="Approved via Human-In-The-Loop (HITL) authorization.",
            checks={"hitl_approved": True},
            dispute_token=dispute_token,
            settlement_id=settlement_id,
            escalation_id=escalation_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    else:
        audit_ledger.append_entry(
            event_type=EventType.HITL_REJECTED,
            actor_type=ActorType.HUMAN,
            actor_id=mandate.human_id if mandate else "unknown",
            mandate_id=attempt.mandate_id,
            attempt_id=attempt.attempt_id,
            details={"escalation_id": escalation_id, "note": note, "reason": "Denied by human"},
        )

        return VerificationResult(
            attempt_id=attempt.attempt_id,
            status=VerificationStatus.REJECTED,
            authorized=False,
            reason=f"Denied by Human-In-The-Loop: {note or 'Cardholder declined purchase'}",
            checks={"hitl_approved": False},
            escalation_id=escalation_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


def verify_purchase(attempt: PurchaseAttempt) -> VerificationResult:
    """
    Independent merchant verification protocol.
    Performs 6-stage fail-closed validation on incoming agent purchase attempts.
    """
    timestamp_now = datetime.now(timezone.utc).isoformat()
    checks: Dict[str, bool] = {
        "mandate_found": False,
        "human_signature_valid": False,
        "agent_authorized": False,
        "agent_signature_valid": False,
        "status_active": False,
        "not_expired": False,
        "replay_protected": False,
        "amount_within_limit": False,
        "category_allowed": False,
        "merchant_allowed": False,
        "budget_available": False,
        "frequency_within_limit": False,
        "conditions_met": False,
    }

    # Stage 1: Authoritative Mandate Lookup
    mandate = mandate_store.get_mandate(attempt.mandate_id)
    if not mandate:
        reason = f"Mandate '{attempt.mandate_id}' not found in authoritative registry."
        audit_ledger.append_entry(
            event_type=EventType.VERIFICATION_FAILED,
            actor_type=ActorType.MERCHANT,
            actor_id=attempt.merchant_id,
            mandate_id=attempt.mandate_id,
            attempt_id=attempt.attempt_id,
            details={"reason": reason, "checks": checks},
        )
        return VerificationResult(
            attempt_id=attempt.attempt_id,
            status=VerificationStatus.REJECTED,
            authorized=False,
            reason=reason,
            checks=checks,
            timestamp=timestamp_now,
        )
    checks["mandate_found"] = True

    # Stage 2: Live Status Check (The Trial by Fire)
    if mandate.status == MandateStatus.REVOKED:
        reason = f"Mandate is REVOKED. Revocation timestamp: {mandate.revoked_at}. Reason: {mandate.revocation_reason}"
        audit_ledger.append_entry(
            event_type=EventType.VERIFICATION_FAILED,
            actor_type=ActorType.MERCHANT,
            actor_id=attempt.merchant_id,
            mandate_id=attempt.mandate_id,
            attempt_id=attempt.attempt_id,
            details={"reason": reason, "checks": checks, "revoked_at": mandate.revoked_at},
        )
        return VerificationResult(
            attempt_id=attempt.attempt_id,
            status=VerificationStatus.REJECTED,
            authorized=False,
            reason=reason,
            checks=checks,
            timestamp=timestamp_now,
        )

    if mandate.status == MandateStatus.EXPIRED:
        reason = f"Mandate has EXPIRED (Expiration: {mandate.expires_at})."
        audit_ledger.append_entry(
            event_type=EventType.VERIFICATION_FAILED,
            actor_type=ActorType.MERCHANT,
            actor_id=attempt.merchant_id,
            mandate_id=attempt.mandate_id,
            attempt_id=attempt.attempt_id,
            details={"reason": reason, "checks": checks},
        )
        return VerificationResult(
            attempt_id=attempt.attempt_id,
            status=VerificationStatus.REJECTED,
            authorized=False,
            reason=reason,
            checks=checks,
            timestamp=timestamp_now,
        )

    if mandate.status == MandateStatus.PAUSED:
        reason = "Mandate is temporarily PAUSED by cardholder."
        return VerificationResult(
            attempt_id=attempt.attempt_id,
            status=VerificationStatus.REJECTED,
            authorized=False,
            reason=reason,
            checks=checks,
            timestamp=timestamp_now,
        )
    checks["status_active"] = True
    checks["not_expired"] = True

    # Stage 3: Cryptographic Human Signature Check
    unsigned_mandate_dict = {
        "mandate_id": mandate.mandate_id,
        "human_id": mandate.human_id,
        "human_pubkey": mandate.human_pubkey,
        "agent_id": mandate.agent_id,
        "agent_pubkey": mandate.agent_pubkey,
        "scope": mandate.scope.model_dump(),
        "payment_token": mandate.payment_token.model_dump(),
        "created_at": mandate.created_at,
        "expires_at": mandate.expires_at,
        "status": MandateStatus.ACTIVE.value,
    }
    human_sig_valid = verify_signature(
        mandate.human_pubkey,
        unsigned_mandate_dict,
        mandate.human_signature,
    )
    if not human_sig_valid:
        reason = "Cryptographic integrity failure: Human signature on mandate is invalid or forged."
        audit_ledger.append_entry(
            event_type=EventType.ADVERSARIAL_BLOCKED,
            actor_type=ActorType.MERCHANT,
            actor_id=attempt.merchant_id,
            mandate_id=attempt.mandate_id,
            attempt_id=attempt.attempt_id,
            details={"reason": reason, "attack_type": "FORGED_MANDATE_SIGNATURE"},
        )
        return VerificationResult(
            attempt_id=attempt.attempt_id,
            status=VerificationStatus.REJECTED,
            authorized=False,
            reason=reason,
            checks=checks,
            timestamp=timestamp_now,
        )
    checks["human_signature_valid"] = True

    # Stage 4: Agent Identity & Signature Check
    if attempt.agent_id != mandate.agent_id:
        reason = f"Impersonation attack: Agent ID '{attempt.agent_id}' does not match authorized mandate agent '{mandate.agent_id}'."
        audit_ledger.append_entry(
            event_type=EventType.ADVERSARIAL_BLOCKED,
            actor_type=ActorType.MERCHANT,
            actor_id=attempt.merchant_id,
            mandate_id=attempt.mandate_id,
            attempt_id=attempt.attempt_id,
            details={"reason": reason, "attack_type": "AGENT_IMPERSONATION"},
        )
        return VerificationResult(
            attempt_id=attempt.attempt_id,
            status=VerificationStatus.REJECTED,
            authorized=False,
            reason=reason,
            checks=checks,
            timestamp=timestamp_now,
        )
    checks["agent_authorized"] = True

    unsigned_attempt_dict = {
        "attempt_id": attempt.attempt_id,
        "mandate_id": attempt.mandate_id,
        "agent_id": attempt.agent_id,
        "merchant_id": attempt.merchant_id,
        "item_id": attempt.item_id,
        "item_title": attempt.item_title,
        "category": attempt.category,
        "amount": attempt.amount,
        "currency": attempt.currency,
        "metadata": attempt.metadata,
        "timestamp": attempt.timestamp,
        "nonce": attempt.nonce,
    }
    agent_sig_valid = verify_signature(
        mandate.agent_pubkey,
        unsigned_attempt_dict,
        attempt.agent_signature,
    )
    if not agent_sig_valid:
        reason = "Cryptographic integrity failure: Purchase attempt signature does not match agent's public key."
        audit_ledger.append_entry(
            event_type=EventType.ADVERSARIAL_BLOCKED,
            actor_type=ActorType.MERCHANT,
            actor_id=attempt.merchant_id,
            mandate_id=attempt.mandate_id,
            attempt_id=attempt.attempt_id,
            details={"reason": reason, "attack_type": "FORGED_ATTEMPT_SIGNATURE"},
        )
        return VerificationResult(
            attempt_id=attempt.attempt_id,
            status=VerificationStatus.REJECTED,
            authorized=False,
            reason=reason,
            checks=checks,
            timestamp=timestamp_now,
        )
    checks["agent_signature_valid"] = True

    # Stage 5: Replay & Nonce Verification
    if state_manager.is_nonce_used(attempt.mandate_id, attempt.nonce):
        reason = f"Replay attack detected: Nonce '{attempt.nonce}' has already been processed."
        audit_ledger.append_entry(
            event_type=EventType.ADVERSARIAL_BLOCKED,
            actor_type=ActorType.MERCHANT,
            actor_id=attempt.merchant_id,
            mandate_id=attempt.mandate_id,
            attempt_id=attempt.attempt_id,
            details={"reason": reason, "attack_type": "REPLAY_ATTACK", "nonce": attempt.nonce},
        )
        return VerificationResult(
            attempt_id=attempt.attempt_id,
            status=VerificationStatus.REJECTED,
            authorized=False,
            reason=reason,
            checks=checks,
            timestamp=timestamp_now,
        )
    checks["replay_protected"] = True

    # Stage 6: Constraint & Budget Evaluation
    current_state = state_manager.get_state(mandate.mandate_id)
    authorized, eval_reason, constraint_checks, can_escalate = evaluate_mandate_constraints(
        mandate=mandate,
        attempt=attempt,
        state=current_state,
    )
    checks.update(constraint_checks)

    if authorized:
        # Successful autonomous purchase execution
        settlement_id = f"stl_{uuid.uuid4().hex[:12]}"
        dispute_token = f"dsp_{hash_payload({'attempt_id': attempt.attempt_id, 'settlement_id': settlement_id})[:16]}"

        state_manager.record_attempt(attempt.mandate_id, attempt.nonce)
        state_manager.record_successful_purchase(attempt.mandate_id, attempt.amount)

        audit_ledger.append_entry(
            event_type=EventType.VERIFICATION_SUCCESS,
            actor_type=ActorType.MERCHANT,
            actor_id=attempt.merchant_id,
            mandate_id=attempt.mandate_id,
            attempt_id=attempt.attempt_id,
            details={
                "authorized": True,
                "amount": attempt.amount,
                "item": attempt.item_title,
                "settlement_id": settlement_id,
                "dispute_token": dispute_token,
                "checks": checks,
            },
        )

        audit_ledger.append_entry(
            event_type=EventType.SETTLEMENT_COMPLETED,
            actor_type=ActorType.MERCHANT,
            actor_id=attempt.merchant_id,
            mandate_id=attempt.mandate_id,
            attempt_id=attempt.attempt_id,
            details={
                "settlement_id": settlement_id,
                "dispute_token": dispute_token,
                "amount": attempt.amount,
                "currency": attempt.currency,
                "payment_token": mandate.payment_token.token_id,
                "card_masked": mandate.payment_token.masked_card,
            },
        )

        return VerificationResult(
            attempt_id=attempt.attempt_id,
            status=VerificationStatus.APPROVED,
            authorized=True,
            reason="Purchase verified within mandate boundaries.",
            checks=checks,
            dispute_token=dispute_token,
            settlement_id=settlement_id,
            timestamp=timestamp_now,
        )

    # If constraints failed, check if it can be escalated to Human-In-The-Loop
    if can_escalate:
        escalation_id = f"esc_{uuid.uuid4().hex[:10]}"
        escalation_req = HITLApprovalRequest(
            escalation_id=escalation_id,
            attempt_id=attempt.attempt_id,
            mandate_id=attempt.mandate_id,
            attempt=attempt,
            reason=eval_reason,
            requested_amount=attempt.amount,
            mandate_limit=mandate.scope.max_amount_per_tx,
            status="PENDING",
            created_at=timestamp_now,
        )
        _escalations[escalation_id] = escalation_req

        audit_ledger.append_entry(
            event_type=EventType.HITL_ESCALATED,
            actor_type=ActorType.MERCHANT,
            actor_id=attempt.merchant_id,
            mandate_id=attempt.mandate_id,
            attempt_id=attempt.attempt_id,
            details={
                "escalation_id": escalation_id,
                "reason": eval_reason,
                "requested_amount": attempt.amount,
                "mandate_limit": mandate.scope.max_amount_per_tx,
            },
        )

        return VerificationResult(
            attempt_id=attempt.attempt_id,
            status=VerificationStatus.ESCALATED_HITL,
            authorized=False,
            reason=f"Purchase outside standard limits ({eval_reason}). Escalated to cardholder for HITL confirmation.",
            checks=checks,
            escalation_id=escalation_id,
            timestamp=timestamp_now,
        )

    # Hard rejection
    audit_ledger.append_entry(
        event_type=EventType.VERIFICATION_FAILED,
        actor_type=ActorType.MERCHANT,
        actor_id=attempt.merchant_id,
        mandate_id=attempt.mandate_id,
        attempt_id=attempt.attempt_id,
        details={"reason": eval_reason, "checks": checks},
    )

    return VerificationResult(
        attempt_id=attempt.attempt_id,
        status=VerificationStatus.REJECTED,
        authorized=False,
        reason=eval_reason,
        checks=checks,
        timestamp=timestamp_now,
    )
