from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from shared.schemas import (
    Mandate,
    CatalogItem,
    PurchaseAttempt,
    VerificationResult,
    HITLApprovalRequest,
    AuditLogEntry,
    DisputeClaim,
    MandateStatus,
)
from mandate.sign import generate_keypair
from mandate.issue import create_mandate
from core.mandate_store import (
    mandate_store,
    create_mandate as store_create_mandate,
    get_mandate as store_get_mandate,
    revoke_mandate as store_revoke_mandate,
)
from core.agent_loop import PurchasingAgent, run_agent
from core.merchant import vuelaya_merchant, get_flights
from core.verify import get_pending_escalations, resolve_escalation, verify_purchase
from core.dispute import dispute_arbiter
from audit.log import audit_ledger
from mandate.adversarial_tests import run_adversarial_suite
from core.seed_loader import load_seed_mandates

app = FastAPI(
    title="AgentBuyer Protocol API",
    description="Cryptographic Mandate & Safe Autonomous Agent Purchasing Circuit",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def load_initial_mandates():
    """Crea estado vivo fresco para cada mandato definido en el archivo semilla."""
    try:
        load_seed_mandates()
    except Exception:
        pass


# Request schemas
class CreateMandateRequest(BaseModel):
    human_id: str = "marta_traveler"
    max_amount_per_tx: float = 150.0
    monthly_budget: float = 500.0
    allowed_categories: List[str] = ["travel", "flights"]
    allowed_merchants: List[str] = ["*"]
    conditions_expression: Optional[str] = "price <= 150 AND destination == 'COR'"
    currency: str = "USD"
    max_executions_per_month: int = 5
    allow_hitl_escalation: bool = True
    validity_days: int = 30
    masked_card: str = "•••• 4242"
    bank_issuer: str = "Galicia AI Payments"


class RevokeMandateRequest(BaseModel):
    reason: str = "Revoked by cardholder (Trial by Fire)"


class ResolveEscalationRequest(BaseModel):
    approved: bool
    note: str = ""


class ExecutePurchaseRequest(BaseModel):
    mandate_id: str
    item_id: str
    agent_id: str = "agent_marta"
    override_amount: Optional[float] = None


class FileDisputeRequest(BaseModel):
    attempt_id: str
    mandate_id: str
    claimant_id: str = "marta_traveler"
    reason: str = "Cardholder disputes transaction"


# Internal test keypairs cache
_key_registry: Dict[str, Dict[str, str]] = {}


def _get_or_create_keys(entity_id: str) -> Dict[str, str]:
    if entity_id not in _key_registry:
        priv, pub = generate_keypair()
        _key_registry[entity_id] = {"priv": priv, "pub": pub}
    return _key_registry[entity_id]


@app.get("/")
def root():
    return {
        "status": "online",
        "system": "AgentBuyer Safe Agentic Purchase Protocol",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


# Mandate Endpoints
@app.post("/mandates/create", response_model=Mandate)
def api_create_mandate(req: CreateMandateRequest):
    h_keys = _get_or_create_keys(req.human_id)
    a_keys = _get_or_create_keys("agent_marta")

    mandate = create_mandate(
        human_id=req.human_id,
        human_privkey=h_keys["priv"],
        human_pubkey=h_keys["pub"],
        agent_id="agent_marta",
        agent_pubkey=a_keys["pub"],
        max_amount_per_tx=req.max_amount_per_tx,
        monthly_budget=req.monthly_budget,
        allowed_categories=req.allowed_categories,
        allowed_merchants=req.allowed_merchants,
        conditions_expression=req.conditions_expression,
        currency=req.currency,
        max_executions_per_month=req.max_executions_per_month,
        allow_hitl_escalation=req.allow_hitl_escalation,
        validity_days=req.validity_days,
        masked_card=req.masked_card,
        bank_issuer=req.bank_issuer,
    )
    mandate_store.save_mandate(mandate)
    return mandate


@app.post("/mandates", status_code=status.HTTP_201_CREATED)
def create_mandate_endpoint(mandate: dict[str, Any]):
    """Crea un mandato firmado y establece su estado vivo inicial."""
    mandate_id = mandate.get("mandate_id")
    if not isinstance(mandate_id, str) or not mandate_id.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El campo mandate_id es obligatorio y debe ser un texto no vacío.",
        )

    try:
        return store_create_mandate(mandate)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error


@app.get("/mandates", response_model=List[Mandate])
def api_list_mandates(human_id: Optional[str] = None):
    return mandate_store.list_mandates(human_id)


@app.get("/mandates/{mandate_id}")
def api_get_mandate(mandate_id: str):
    mandate = mandate_store.get_mandate(mandate_id)
    if not mandate:
        # Check dictionary store
        rec = store_get_mandate(mandate_id)
        if rec:
            return rec
        raise HTTPException(status_code=404, detail="Mandate not found")
    return mandate


@app.post("/mandates/{mandate_id}/revoke")
def api_revoke_mandate(mandate_id: str, req: Optional[RevokeMandateRequest] = None):
    reason = req.reason if req else "Revocado por el usuario"
    success = mandate_store.revoke_mandate(mandate_id, reason)
    store_revoke_mandate(mandate_id)
    if not success:
        raise HTTPException(status_code=404, detail="Mandate not found")
    return {"status": "REVOKED", "mandate_id": mandate_id, "reason": reason}


@app.post("/mandates/{mandate_id}/pause")
def api_pause_mandate(mandate_id: str):
    success = mandate_store.pause_mandate(mandate_id)
    if not success:
        raise HTTPException(status_code=404, detail="Mandate not found")
    return {"status": "PAUSED", "mandate_id": mandate_id}


@app.post("/mandates/{mandate_id}/resume")
def api_resume_mandate(mandate_id: str):
    success = mandate_store.resume_mandate(mandate_id)
    if not success:
        raise HTTPException(status_code=404, detail="Mandate not found")
    return {"status": "ACTIVE", "mandate_id": mandate_id}


# Merchant & Purchasing Endpoints
@app.get("/merchant/catalog", response_model=List[CatalogItem])
def api_get_catalog():
    return vuelaya_merchant.get_catalog()


@app.get("/merchant/flights")
def api_get_flights():
    return get_flights()


@app.post("/agent/run")
def api_run_agent(payload: dict):
    mandate_id = payload.get("mandate_id")
    if not mandate_id:
        raise HTTPException(status_code=422, detail="mandate_id is required")
    return run_agent(mandate_id)


@app.post("/purchases/execute")
def api_execute_purchase(req: ExecutePurchaseRequest):
    mandate = mandate_store.get_mandate(req.mandate_id)
    if not mandate:
        raise HTTPException(status_code=404, detail="Mandate not found")

    item = vuelaya_merchant.get_item(req.item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found in catalog")

    a_keys = _get_or_create_keys(req.agent_id)
    agent = PurchasingAgent(req.agent_id, a_keys["priv"], a_keys["pub"])

    attempt, result = agent.attempt_purchase(
        mandate=mandate,
        item=item,
        merchant=vuelaya_merchant,
        override_amount=req.override_amount,
    )

    return {
        "attempt": attempt,
        "verification_result": result,
    }


# Human-In-The-Loop Escalation Endpoints
@app.get("/escalations/pending", response_model=List[HITLApprovalRequest])
def api_get_pending_escalations(mandate_id: Optional[str] = None):
    return get_pending_escalations(mandate_id)


@app.post("/escalations/{escalation_id}/resolve")
def api_resolve_escalation(escalation_id: str, req: ResolveEscalationRequest):
    h_keys = _get_or_create_keys("marta_traveler")
    res = resolve_escalation(
        escalation_id=escalation_id,
        approved=req.approved,
        human_privkey=h_keys["priv"],
        human_pubkey=h_keys["pub"],
        note=req.note,
    )
    if not res:
        raise HTTPException(status_code=404, detail="Escalation request not found or already resolved")
    return res


# Audit Ledger Endpoints
@app.get("/audit/trail")
def api_get_audit_trail(
    role: str = Query(default="auditor", pattern="^(human|merchant|auditor)$"),
    mandate_id: Optional[str] = None,
    attempt_id: Optional[str] = None,
):
    return audit_ledger.get_trail_for(role=role, mandate_id=mandate_id, attempt_id=attempt_id)


@app.get("/audit/verify")
def api_verify_audit_integrity():
    is_valid, msg = audit_ledger.verify_chain_integrity()
    return {"valid": is_valid, "message": msg, "total_blocks": len(audit_ledger._entries)}


# Dispute Resolution Endpoints
@app.post("/disputes/file", response_model=DisputeClaim)
def api_file_dispute(req: FileDisputeRequest):
    return dispute_arbiter.file_dispute(
        attempt_id=req.attempt_id,
        mandate_id=req.mandate_id,
        claimant_id=req.claimant_id,
        reason=req.reason,
    )


@app.get("/disputes", response_model=List[DisputeClaim])
def api_list_disputes():
    return dispute_arbiter.list_disputes()


# Adversarial Suite Runner
@app.post("/adversarial/run")
def api_run_adversarial():
    success = run_adversarial_suite()
    return {
        "success": success,
        "message": "All 8 attack vectors evaluated." if success else "Some attacks breached perimeter.",
    }


# Include modular routers if present
try:
    from api.verify import router as verify_router
    app.include_router(verify_router)
except ImportError:
    pass

try:
    from api.agent import router as agent_router
    app.include_router(agent_router)
except ImportError:
    pass

try:
    from api.merchant import router as merchant_router
    app.include_router(merchant_router)
except ImportError:
    pass
