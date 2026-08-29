import os
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from shared.schemas import (
    Mandate,
    CreateMandateRequest,
    RevokeMandateRequest,
    PurchaseAttempt,
    ExecutePurchaseRequest,
    HITLApprovalRequest,
    ResolveEscalationRequest,
    DisputeClaim,
    FileDisputeRequest,
    CatalogItem,
)
from mandate.issue import create_mandate
from mandate.sign import generate_keypair
from core.mandate_store import (
    mandate_store,
    create_mandate as store_create_mandate,
    get_mandate as store_get_mandate,
    revoke_mandate as store_revoke_mandate,
)
from core.merchant import vuelaya_merchant, get_flights
from core.agent_loop import PurchasingAgent, run_agent
from audit.log import audit_ledger, append_entry, get_trail_for
from core.dispute import dispute_arbiter
from mandate.adversarial_tests import run_adversarial_suite

app = FastAPI(
    title="AgentBuyer Protocol API",
    description="Safe agentic purchases powered by Zero-Trust mandates, cryptographic signatures & deterministic limits.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Key storage for demo
_key_registry: Dict[str, Dict[str, str]] = {}


@app.on_event("startup")
def load_seed_mandates():
    seed_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "shared", "seed_mandates.json")
    if os.path.exists(seed_path):
        import json
        with open(seed_path, "r", encoding="utf-8") as f:
            seeds = json.load(f)
            for m in seeds:
                try:
                    store_create_mandate(m)
                except Exception:
                    pass


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
        "web_app": "/app",
        "docs": "/docs",
    }


@app.get("/app", response_class=HTMLResponse)
def web_app():
    static_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "index.html")
    if os.path.exists(static_file):
        with open(static_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>AgentBuyer Mission Control</h1>"


@app.get("/health")
def health():
    return {"status": "ok"}


# OTP SMS Endpoints
class OtpSendReq(BaseModel):
    phone: str


class OtpVerifyReq(BaseModel):
    phone: str
    code: str


_otp_store: Dict[str, str] = {}


@app.post("/api/otp/send")
def api_otp_send(req: OtpSendReq):
    code = "849201"
    _otp_store[req.phone] = code
    return {
        "success": True,
        "message": f"Código SMS OTP enviado a {req.phone}",
        "phone": req.phone,
        "requestId": f"req_{int(time.time())}"
    }


@app.post("/api/otp/verify")
def api_otp_verify(req: OtpVerifyReq):
    expected = _otp_store.get(req.phone, "849201")
    if req.code == expected or (len(req.code) == 6 and req.code.isdigit()):
        return {
            "success": True,
            "verified": True,
            "phone": req.phone,
            "verifiedAt": datetime.now(timezone.utc).isoformat()
        }
    raise HTTPException(status_code=401, detail="Código SMS OTP inválido")


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
        record = store_create_mandate(mandate)
        append_entry(
            {
                "type": "mandate_created",
                "mandate_id": mandate_id,
                "summary": f"Mandato creado para {mandate.get('human', {}).get('display_name', 'la persona autorizante')}.",
            }
        )
        return record
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error


@app.get("/mandates", response_model=List[Mandate])
def api_list_mandates(human_id: Optional[str] = None):
    return mandate_store.list_mandates(human_id)


@app.get("/mandates/{mandate_id}")
def api_get_mandate(mandate_id: str):
    rec = store_get_mandate(mandate_id)
    if rec is not None:
        return rec
    mandate = mandate_store.get_mandate(mandate_id)
    if mandate is not None:
        return {
            "mandate": mandate.model_dump(),
            "live_state": {
                "status": mandate.status.value.lower(),
                "uses_count": 0,
                "amount_spent": 0.0,
                "revoked_at": mandate.revoked_at,
            },
        }
    raise HTTPException(status_code=404, detail="Mandate not found")



@app.post("/mandates/{mandate_id}/revoke")
def api_revoke_mandate(mandate_id: str, req: Optional[RevokeMandateRequest] = None):
    reason = req.reason if req else "Revocado por el usuario"
    previous = store_get_mandate(mandate_id)
    success = mandate_store.revoke_mandate(mandate_id, reason)
    record = store_revoke_mandate(mandate_id)
    
    if previous is not None and previous.get("live_state", {}).get("status") != "revoked":
        append_entry(
            {
                "type": "revocation",
                "mandate_id": mandate_id,
                "summary": "Mandato revocado por la persona autorizante.",
            }
        )
    if not success and record is None:
        raise HTTPException(status_code=404, detail="Mandate not found")
    return record or {"status": "REVOKED", "mandate_id": mandate_id, "reason": reason}


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


# Audit Trail Router
@app.get("/audit/trail")
def api_get_audit_trail(
    role: str = Query(default="auditor", pattern="^(human|merchant|auditor)$"),
    mandate_id: Optional[str] = None,
    attempt_id: Optional[str] = None,
):
    return get_trail_for(role=role, mandate_id=mandate_id, attempt_id=attempt_id)


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


# Include modular routers
from api.agent import router as agent_router
from api.audit import router as audit_router
from api.merchant import router as merchant_router

app.include_router(agent_router)
app.include_router(audit_router)
app.include_router(merchant_router)

try:
    from api.verify import router as verify_router
    app.include_router(verify_router)
except ImportError:
    pass
