from typing import Any

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from audit.log import append_entry
from core.mandate_store import create_mandate, get_mandate, revoke_mandate
from core.seed_loader import load_seed_mandates


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def load_initial_mandates():
    """Crea estado vivo fresco para cada mandato definido en el archivo semilla."""
    load_seed_mandates()


@app.get("/health")
def health():
    return {"status": "ok"}


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
        record = create_mandate(mandate)
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


@app.get("/mandates/{mandate_id}")
def get_mandate_endpoint(mandate_id: str):
    """Devuelve el mandato y su estado vivo actual."""
    record = get_mandate(mandate_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mandato no encontrado.")
    return record


@app.post("/mandates/{mandate_id}/revoke")
def revoke_mandate_endpoint(mandate_id: str):
    """Revoca el mandato inmediatamente en la fuente de verdad en memoria."""
    previous = get_mandate(mandate_id)
    record = revoke_mandate(mandate_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mandato no encontrado.")
    if previous is not None and previous["live_state"]["status"] != "revoked":
        append_entry(
            {
                "type": "revocation",
                "mandate_id": mandate_id,
                "summary": "Mandato revocado por la persona autorizante.",
            }
        )
    return record


# El endpoint de verificación vive separado para no mezclarlo con Fase 1.
from api.verify import router as verify_router

app.include_router(verify_router)

# Comercio y agente de la demo de Fase 3.
from api.agent import router as agent_router
from api.audit import router as audit_router
from api.merchant import router as merchant_router

app.include_router(agent_router)
app.include_router(audit_router)
app.include_router(merchant_router)
