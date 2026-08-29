from typing import Any

from fastapi import FastAPI, HTTPException, status

from core.mandate_store import create_mandate, get_mandate, revoke_mandate


app = FastAPI()


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
        return create_mandate(mandate)
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
    record = revoke_mandate(mandate_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mandato no encontrado.")
    return record


# El endpoint de verificación vive separado para no mezclarlo con Fase 1.
from api.verify import router as verify_router

app.include_router(verify_router)

# Comercio y agente de la demo de Fase 3.
from api.agent import router as agent_router
from api.merchant import router as merchant_router

app.include_router(agent_router)
app.include_router(merchant_router)
