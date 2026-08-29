"""Almacenamiento en memoria para mandatos y su estado vivo."""

from copy import deepcopy
from datetime import datetime, timezone


# Esta es la única fuente de verdad del estado vivo durante la ejecución.
# No se debe cachear su contenido en los endpoints de verificación futuros.
MANDATES: dict[str, dict] = {}

def create_mandate(mandate: dict) -> dict:
    """Guarda un mandato nuevo con su estado vivo inicial."""
    mandate_id = mandate["mandate_id"]
    if mandate_id in MANDATES:
        raise ValueError("El mandate_id ya existe")

    MANDATES[mandate_id] = {
        "mandate": deepcopy(mandate),
        "live_state": {
            "status": "active",
            "uses_count": 0,
            "amount_spent": 0,
            "revoked_at": None,
        },
    }
    return get_mandate(mandate_id)


def get_mandate(mandate_id: str) -> dict | None:
    """Lee el mandato y su estado actual directamente del almacenamiento."""
    record = MANDATES.get(mandate_id)
    return deepcopy(record) if record is not None else None


def revoke_mandate(mandate_id: str) -> dict | None:
    """Revoca un mandato; los intentos posteriores deben leer este cambio fresco."""
    record = MANDATES.get(mandate_id)
    if record is None:
        return None

    live_state = record["live_state"]
    if live_state["status"] != "revoked":
        live_state["status"] = "revoked"
        live_state["revoked_at"] = datetime.now(timezone.utc).isoformat()

    return get_mandate(mandate_id)


def apply_approved_purchase(mandate_id: str, amount: int | float) -> dict | None:
    """Actualiza el estado vivo solo después de una aprobación final."""
    record = MANDATES.get(mandate_id)
    if record is None:
        return None

    # Esta lectura y escritura ocurre sobre el registro vivo, no sobre una copia.
    record["live_state"]["uses_count"] += 1
    record["live_state"]["amount_spent"] += amount
    return get_mandate(mandate_id)


