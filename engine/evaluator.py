"""evaluate(mandate, live_state, attempt) -> dict — THE contracted entry point.

Orchestrates: amount → category → merchant → uses → each condition →
assemble checks[] → assign verdict → reason.

Contract (agreed with core/):
- Always returns the full dict shape. Never None, never a bare bool,
  never an uncaught exception.
- All checks pass          -> "APPROVE"
- Any check fails          -> "ESCALATE" (soft violation, human can approve)
- Internal error           -> "REJECT" with an error-explaining check
  (hard REJECTs for bad signature / revoked / expired happen upstream in core/,
  before this engine is ever called).
"""
from __future__ import annotations

from typing import Any


def _normalize_attempt(attempt: dict) -> dict:
    """Acepta el shape plano del contrato Y el anidado que envía core/
    ({"purchase": {...}}) — el engine es defensivo con cualquiera de los dos."""
    purchase = attempt.get("purchase")
    if isinstance(purchase, dict):
        return purchase
    return attempt


def _fmt(n: Any) -> str: #make it string
    """150.0 -> '150', 149.99 -> '149.99' — keeps details readable in the demo UI."""
    if isinstance(n, float) and n == int(n):
        return str(int(n))
    return str(n)


def _check_amount(constraints: dict, live_state: dict, attempt: dict) -> dict:
    cap = constraints["max_amount_per_purchase"]
    amount = attempt.get("amount")
    ok = amount is not None and amount <= cap
    detail = (
        f"{_fmt(amount)} <= {_fmt(cap)}" if ok
        else f"{_fmt(amount)} excede el máximo de {_fmt(cap)}"
    )
    return {"rule": "amount", "pass": ok, "detail": detail}


def _check_category(constraints: dict, live_state: dict, attempt: dict) -> dict:
    allowed = constraints["allowed_categories"]
    category = attempt.get("category")
    ok = category in allowed
    detail = f"{category} permitida" if ok else f"{category} no está en {allowed}"
    return {"rule": "category", "pass": ok, "detail": detail}


def _check_merchant(constraints: dict, live_state: dict, attempt: dict) -> dict:
    allowed = constraints["allowed_merchants"]
    merchant = attempt.get("merchant_id")
    # lista vacia = cualquier comercio pasa (acordado en el contrato).
    ok = not allowed or merchant in allowed
    detail = f"{merchant} permitido" if ok else f"{merchant} no está en {allowed}"
    return {"rule": "merchant", "pass": ok, "detail": detail}


def _check_uses(constraints: dict, live_state: dict, attempt: dict) -> dict:
    max_uses = constraints["max_uses"]
    used = live_state.get("uses_count", 0)
    ok = used < max_uses
    detail = f"{used}/{max_uses}" if ok else f"usos agotados ({used}/{max_uses})"
    return {"rule": "uses", "pass": ok, "detail": detail}


def _check_condition_price_below(condition: dict, live_state: dict, attempt: dict) -> dict:
    limit = condition["value"]
    price = attempt.get("metadata", {}).get("price", attempt.get("amount"))
    ok = price is not None and price < limit
    detail = (
        f"{_fmt(price)} < {_fmt(limit)}" if ok
        else f"{_fmt(price)} no es menor que {_fmt(limit)}"
    )
    return {"rule": "condition.price_below", "pass": ok, "detail": detail}


# TODO(paso 2 del build order): mover el dispatch de condiciones a conditions.py
# para registrar tipos nuevos (frequency_per_month, ...) sin tocar este loop.
_CONDITION_CHECKS = {
    "price_below": _check_condition_price_below,
}

_CONSTRAINT_CHECKS = [
    ("max_amount_per_purchase", _check_amount),
    ("allowed_categories", _check_category),
    ("allowed_merchants", _check_merchant),
    ("max_uses", _check_uses),
]


def evaluate(mandate: dict, live_state: dict, attempt: dict) -> dict:
    try:
        constraints = mandate.get("constraints", {})
        attempt = _normalize_attempt(attempt)
        checks: list[dict] = []

        for key, check_fn in _CONSTRAINT_CHECKS:
            if key in constraints:
                checks.append(check_fn(constraints, live_state, attempt))

        for condition in constraints.get("conditions", []):
            cond_type = condition.get("type")
            check_fn = _CONDITION_CHECKS.get(cond_type)
            if check_fn is None:
                # Condición que no sabemos evaluar: fail-closed como check fallido.
                checks.append({
                    "rule": f"condition.{cond_type}",
                    "pass": False,
                    "detail": f"tipo de condición desconocido: {cond_type!r}",
                })
            else:
                checks.append(check_fn(condition, live_state, attempt))

        failed = [c for c in checks if not c["pass"]]
        if not failed:
            verdict = "APPROVE"
            reason = "Todas las restricciones satisfechas"
        else:
            verdict = "ESCALATE"
            reason = (
                "Requiere aprobación humana: falló "
                + ", ".join(c["rule"] for c in failed)
            )
        return {"verdict": verdict, "checks": checks, "reason": reason}

    except Exception as exc:  # el contrato prohíbe propagar excepciones
        return {
            "verdict": "REJECT",
            "checks": [{
                "rule": "engine.internal_error",
                "pass": False,
                "detail": f"{type(exc).__name__}: {exc}",
            }],
            "reason": "Error interno del motor de restricciones — rechazado por seguridad",
        }
