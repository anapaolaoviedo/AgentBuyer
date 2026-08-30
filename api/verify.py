"""Endpoint que orquesta la verificación segura de un intento de compra."""

from datetime import datetime, timezone
from numbers import Real
from typing import Any

from fastapi import APIRouter, HTTPException, status

from audit.log import append_entry
from core.mandate_store import (
    apply_approved_purchase,
    get_mandate,
)
# El engine real decide restricciones; el mock queda disponible para demos aisladas.
from engine.evaluator import evaluate


router = APIRouter()


def _timestamp() -> str:
    """Genera timestamps explícitamente en UTC para respuestas y auditoría."""
    return datetime.now(timezone.utc).isoformat()


def _finish(
    mandate_id: str,
    attempt_id: str,
    verdict: str,
    checks: list[dict],
    human_readable: str,
    amount: int | float | None = None,
) -> dict:
    """Registra toda decisión antes de devolverla al comercio."""
    decided_at = _timestamp()
    append_entry(
        {
            "type": "verification",
            "mandate_id": mandate_id,
            "attempt_id": attempt_id,
            "verdict": verdict,
            "summary": human_readable,
            # Datos para la revisión humana de escalaciones (api/escalations.py):
            "amount": amount,
            "failed_rules": [c["rule"] for c in checks if not c.get("pass")],
        }
    )
    return {
        "attempt_id": attempt_id,
        "mandate_id": mandate_id,
        "verdict": verdict,
        "checks": checks,
        "human_readable": human_readable,
        "decided_at": decided_at,
    }


@router.post("/verify")
def verify_purchase(attempt_purchase: dict[str, Any]):
    """Verifica seguridad primero y delega restricciones al engine después."""
    attempt_id = str(attempt_purchase.get("attempt_id", ""))
    mandate_id = str(attempt_purchase.get("mandate_id", ""))

    # 1. Se consulta siempre el registro actual; no hay caché de mandatos.
    record = get_mandate(mandate_id)
    if record is None:
        return _finish(
            mandate_id,
            attempt_id,
            "REJECT",
            [{"rule": "mandate_exists", "pass": False, "detail": "Mandato no encontrado."}],
            "Compra rechazada: el mandato no existe.",
        )

    mandate = record["mandate"]
    live_state = record["live_state"]
    security_checks: list[dict] = []

    # 2a. La comprobación criptográfica real se conectará en una fase posterior.
    signature = mandate.get("signature")
    if not isinstance(signature, str) or not signature.strip():
        security_checks.append(
            {"rule": "signature", "pass": False, "detail": "Firma ausente o vacía."}
        )
        return _finish(
            mandate_id,
            attempt_id,
            "REJECT",
            security_checks,
            "Compra rechazada: la firma del mandato no es válida.",
        )
    security_checks.append({"rule": "signature", "pass": True, "detail": "Firma presente."})

    # 2b. El agente que presenta el intento debe ser el autorizado en el mandato.
    expected_agent_id = mandate.get("agent", {}).get("id")
    presented_agent_id = attempt_purchase.get("presented_by_agent")
    if presented_agent_id != expected_agent_id:
        security_checks.append(
            {
                "rule": "agent_identity",
                "pass": False,
                "detail": "El agente que presenta el intento no está autorizado.",
            }
        )
        return _finish(
            mandate_id,
            attempt_id,
            "REJECT",
            security_checks,
            "Compra rechazada: el agente no coincide con el mandato.",
        )
    security_checks.append(
        {"rule": "agent_identity", "pass": True, "detail": "Agente autorizado."}
    )

    # 2c. live_state proviene de la lectura fresca realizada al inicio de este intento.
    if live_state["status"] == "revoked":
        security_checks.append(
            {"rule": "status", "pass": False, "detail": "mandato revocado"}
        )
        return _finish(
            mandate_id,
            attempt_id,
            "REJECT",
            security_checks,
            "Compra rechazada: el mandato está revocado.",
        )
    if live_state["status"] == "expired":
        security_checks.append(
            {"rule": "status", "pass": False, "detail": "mandato expirado"}
        )
        return _finish(
            mandate_id,
            attempt_id,
            "REJECT",
            security_checks,
            "Compra rechazada: el mandato está expirado.",
        )
    security_checks.append({"rule": "status", "pass": True, "detail": "Mandato activo."})

    # 3. El engine recibe el intento de compra plano de su contrato: category,
    # merchant_id, amount y metadata.price, nunca el envoltorio HTTP completo.
    engine_attempt = attempt_purchase.get("purchase", {})
    if not isinstance(engine_attempt, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="purchase debe ser un objeto.",
        )
    engine_result = evaluate(mandate, live_state, engine_attempt)
    verdict = engine_result["verdict"]
    checks = security_checks + engine_result["checks"]

    amount = engine_attempt.get("amount")
    if not isinstance(amount, Real) or isinstance(amount, bool):
        amount = None

    # 5. La actualización se aplica sobre el estado vivo, únicamente al aprobar.
    if verdict == "APPROVE":
        if amount is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="purchase.amount debe ser un número.",
            )
        apply_approved_purchase(mandate_id, amount)
        human_readable = "Compra aprobada por el mandato."
    else:
        human_readable = "La compra requiere aprobación humana."

    # 4 y 6. El veredicto final es el del engine y combina todos los checks.
    return _finish(mandate_id, attempt_id, verdict, checks, human_readable, amount=amount)
