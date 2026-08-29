import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

from shared.schemas import Mandate, MandateScope, MandateStatus, PaymentToken
from mandate.sign import sign_payload


def create_mandate(
    human_id: str,
    human_privkey: str,
    human_pubkey: str,
    agent_id: str,
    agent_pubkey: str,
    max_amount_per_tx: float,
    monthly_budget: float = 500.0,
    allowed_categories: Optional[List[str]] = None,
    allowed_merchants: Optional[List[str]] = None,
    conditions_expression: Optional[str] = None,
    currency: str = "USD",
    max_executions_per_month: int = 5,
    allow_hitl_escalation: bool = True,
    validity_days: int = 30,
    masked_card: str = "•••• 4242",
    bank_issuer: str = "Galicia AI Payments",
) -> Mandate:
    """
    Creates and digitally signs a new purchase mandate.
    Zero raw card details are stored: a cryptographically bound scoped payment token is generated.
    """
    if allowed_categories is None:
        allowed_categories = ["travel", "flights"]
    if allowed_merchants is None:
        allowed_merchants = ["*"]

    mandate_id = f"mnd_{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=validity_days)

    scope = MandateScope(
        max_amount_per_tx=max_amount_per_tx,
        monthly_budget=monthly_budget,
        allowed_categories=allowed_categories,
        allowed_merchants=allowed_merchants,
        conditions_expression=conditions_expression,
        currency=currency,
        max_executions_per_month=max_executions_per_month,
        allow_hitl_escalation=allow_hitl_escalation,
    )

    payment_token = PaymentToken(
        token_id=f"vtok_{uuid.uuid4().hex[:12]}",
        token_type="SCOPED_VIRTUAL_TOKEN",
        masked_card=masked_card,
        bank_issuer=bank_issuer,
        expires_at=expires_at.isoformat(),
        bound_mandate_id=mandate_id,
    )

    unsigned_mandate_dict: Dict[str, Any] = {
        "mandate_id": mandate_id,
        "human_id": human_id,
        "human_pubkey": human_pubkey,
        "agent_id": agent_id,
        "agent_pubkey": agent_pubkey,
        "scope": scope.model_dump(),
        "payment_token": payment_token.model_dump(),
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "status": MandateStatus.ACTIVE.value,
    }

    # Digital signature by the human binding all terms and payment token
    signature = sign_payload(human_privkey, unsigned_mandate_dict)

    mandate = Mandate(
        mandate_id=mandate_id,
        human_id=human_id,
        human_pubkey=human_pubkey,
        agent_id=agent_id,
        agent_pubkey=agent_pubkey,
        scope=scope,
        payment_token=payment_token,
        created_at=now.isoformat(),
        expires_at=expires_at.isoformat(),
        status=MandateStatus.ACTIVE,
        human_signature=signature,
    )

    return mandate
