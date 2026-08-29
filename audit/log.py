"""Trail de auditoría append-only compartido por todo el sistema."""

from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4


_EVENT_TYPES = {
    "mandate_created",
    "verification",
    "revocation",
    "purchase_completed",
    "agent_run",
}

# Se agrega únicamente con append_entry; no existe una operación de borrado.
AUDIT_TRAIL: list[dict] = []


def append_entry(event: dict) -> dict:
    """Agrega un evento inmutable para los consumidores del trail de auditoría."""
    event_type = event.get("type")
    if event_type not in _EVENT_TYPES:
        raise ValueError(f"Tipo de evento de auditoría inválido: {event_type!r}")
    if "mandate_id" not in event or "summary" not in event:
        raise ValueError("Todo evento requiere mandate_id y summary.")

    entry = deepcopy(event)
    entry["event_id"] = f"evt_{uuid4().hex}"
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    AUDIT_TRAIL.append(entry)
    return deepcopy(entry)


def get_trail_for(role: str, mandate_id: str | None = None) -> list[dict]:
    """Lee el trail descendente y aplica la visibilidad del rol solicitado."""
    if role == "auditor":
        entries = AUDIT_TRAIL
    elif role in {"human", "merchant"}:
        entries = [entry for entry in AUDIT_TRAIL if mandate_id and entry["mandate_id"] == mandate_id]
    else:
        raise ValueError("role debe ser human, merchant o auditor.")

    return deepcopy(sorted(entries, key=lambda entry: entry["timestamp"], reverse=True))
