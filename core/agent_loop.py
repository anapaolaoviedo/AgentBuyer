"""Ciclo del agente comprador que consume el comercio y la verificación."""

from numbers import Real
from uuid import uuid4

from audit.log import append_entry
from core.mandate_store import get_mandate
from core.merchant import get_flights
from core.merchant_search import _merchant_slug, search_merchant_offers


def _discover_flights(search_fields: dict | None) -> tuple[list[dict], str]:
    """Descubre vuelos: búsqueda web real si hay campos; mock como respaldo.

    El mock (catálogo VuelaYa) queda como fallback deliberado: si la búsqueda
    real falla o no hay red (wifi de conferencia), la demo sigue funcionando.
    """
    if isinstance(search_fields, dict) and search_fields:
        offers = search_merchant_offers("flights", search_fields)
        if offers:
            route = f"{search_fields.get('origin', '?')}->{search_fields.get('destination', '?')}"
            flights = [
                {
                    "id": f"web_{index}",
                    "route": route,
                    "price": offer["price"],
                    "category": "travel.flights",
                    "merchant_id": _merchant_slug(offer["merchant"]),
                    "merchant": offer["merchant"],
                    "details": offer["details"],
                    "url": offer["url"],
                    "source": "web",
                }
                for index, offer in enumerate(offers)
            ]
            return flights, "web"
    mock_flights = [
        flight | {"source": "mock", "merchant": "VuelaYa"} for flight in get_flights()
    ]
    return mock_flights, "mock"


def _price_limit(mandate: dict) -> int | float | None:
    """Lee price_below con el contrato de constraints del engine."""
    constraints = mandate.get("constraints", {})
    conditions = constraints.get("conditions", []) if isinstance(constraints, dict) else []
    for condition in conditions:
        if not isinstance(condition, dict) or condition.get("type") != "price_below":
            continue
        candidate = condition.get("value")
        if isinstance(candidate, Real) and not isinstance(candidate, bool):
            return candidate
    return None


def run_agent(mandate_id: str, search_fields: dict | None = None) -> dict:
    """Descubre, decide, intenta y registra el resultado de una compra.

    Con search_fields ({origin, destination, departure_date, ...}) descubre
    ofertas REALES vía web search; sin ellos (o si la búsqueda falla) usa el
    catálogo mock de VuelaYa, como siempre.
    """
    flights_seen, discovery_source = _discover_flights(search_fields)
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
            "metadata": {
                "flight_id": selected_flight["id"],
                "price": selected_flight["price"],
                "source": selected_flight["source"],
                **({"url": selected_flight["url"]} if selected_flight.get("url") else {}),
            },
        },
    }

    # Importación local para que el agente sea cliente de la lógica pública de verify.
    from api.verify import verify_purchase

    verification = verify_purchase(attempt)
    verdict = verification["verdict"]
    completed = verdict == "APPROVE"

    source_label = "en la web (búsqueda real)" if discovery_source == "web" else "en el catálogo demo"
    story = (
        f"Encontró {len(flights_seen)} vuelos {source_label}. "
        + (f"Aplicó el límite price_below de {limit} USD y " if limit is not None else "No encontró un límite price_below utilizable y ")
        + f"eligió {selected_flight['id']} ({selected_flight['route']}) por {selected_flight['price']} USD. "
        + ("La compra fue completada tras recibir APPROVE." if completed else f"La compra no procedió: verify devolvió {verdict}. {verification['human_readable']}")
    )
    # Además del evento de verify, queda registrada la corrida completa del agente.
    append_entry(
        {
            "type": "agent_run",
            "mandate_id": mandate_id,
            "attempt_id": attempt_id,
            "verdict": verdict,
            "summary": story,
        }
    )
    if completed:
        append_entry(
            {
                "type": "purchase_completed",
                "mandate_id": mandate_id,
                "attempt_id": attempt_id,
                "verdict": "APPROVE",
                "summary": f"Compra completada por Saturday: {selected_flight['route']} por {selected_flight['price']} USD.",
            }
        )
    return {
        "mandate_id": mandate_id,
        "attempt_id": attempt_id,
        "discovery_source": discovery_source,
        "flights_seen": flights_seen,
        "selected_flight": selected_flight,
        "selection_reason": "Vuelo más barato dentro de price_below." if eligible else "No hubo vuelo dentro de price_below; se intentó el más barato disponible.",
        "attempt": attempt,
        "verification": verification,
        "purchase_completed": completed,
        "human_readable": story,
    }
