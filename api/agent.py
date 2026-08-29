"""API para ejecutar una corrida completa del agente comprador."""

from typing import Any

from fastapi import APIRouter, HTTPException, status

from core.agent_loop import run_agent


router = APIRouter()


@router.post("/agent/run")
def run_buyer_agent(request: dict[str, Any]):
    """Hace que el agente descubra vuelos, decida y presente una compra."""
    mandate_id = request.get("mandate_id")
    if not isinstance(mandate_id, str) or not mandate_id.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="El campo mandate_id es obligatorio y debe ser un texto no vacío.")
    return run_agent(mandate_id)
