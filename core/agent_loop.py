"""Ciclo del agente comprador que consume el comercio y la verificación."""

from datetime import datetime, timezone
from numbers import Real
from uuid import uuid4

from core.mandate_store import VERIFICATION_EVENTS, get_mandate
from core.merchant import get_flights


def _price_limit(mandate: dict) -> int | float | None:
    """Obtiene price_below de formatos simples usados en los mandatos de demo."""
    conditions = mandate.get("conditions")
    limits = mandate.get("limits")
    candidates = [
        mandate.get("price_below"),
        conditions.get("price_below") if isinstance(conditions, dict) else None,
        limits.get("price_below") if isinstance(limits, dict) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, Real) and not isinstance(candidate, bool):
            return candidate
    return None


def run_agent(mandate_id: str) -> dict:
    """Descubre, decide, intenta y registra el resultado de una compra."""
    # Descubrimiento: la misma función respalda GET /merchant/flights.
    flights_seen = get_flights()
    record = get_mandate(mandate_id)
    mandate = record["mandate"] if record is not None else {}
    limit = _price_limit(mandate)

    # Decisión: por debajo del límite si existe; si no, se intenta el más barato.
    eligible = [flight for flight in flights_seen if limit is not None and flight["price"] < limit]
    selected_flight = min(eligible or flights_seen, key=lambda flight: flight["price"])
    attempt_id = f"att_agent_{uuid4().hex[:12]}"
    agent_id = mandate.get("agent", {}).get("id", "")
    attempt = {
        "attempt_id": attempt_id,
        "mandate_id": mandate_id,
        "presented_by_agent": agent_id,
        "purchase": {
            "merchant_id": selected_flight["merchant_id"],
            "category": selected_flight["category"],
            "amount": selected_flight["price"],
            "currency": "USD",
            "description": f"Vuelo {selected_flight['route']}",
            "metadata": {"flight_id": selected_flight["id"], "price": selected_flight["price"]},
        },
    }

    # Importación local para que el agente sea cliente de la lógica pública de verify.
    from api.verify import verify_purchase

    verification = verify_purchase(attempt)
    verdict = verification["verdict"]
    completed = verdict == "APPROVE"

    # Además del evento de /verify, se registra explícitamente la corrida del agente.
    VERIFICATION_EVENTS.append(
        {
            "mandate_id": mandate_id,
            "attempt_id": attempt_id,
            "verdict": verdict,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "agent_run",
        }
    )

    story = (
        f"Encontró {len(flights_seen)} vuelos. "
        + (f"Aplicó el límite price_below de {limit} USD y " if limit is not None else "No encontró un límite price_below utilizable y ")
        + f"eligió {selected_flight['id']} ({selected_flight['route']}) por {selected_flight['price']} USD. "
        + ("La compra fue completada tras recibir APPROVE." if completed else f"La compra no procedió: verify devolvió {verdict}. {verification['human_readable']}")
    )
    return {
        "mandate_id": mandate_id,
        "attempt_id": attempt_id,
        "flights_seen": flights_seen,
        "selected_flight": selected_flight,
        "selection_reason": "Vuelo más barato dentro de price_below." if eligible else "No hubo vuelo dentro de price_below; se intentó el más barato disponible.",
        "attempt": attempt,
        "verification": verification,
        "purchase_completed": completed,
        "human_readable": story,
    }
