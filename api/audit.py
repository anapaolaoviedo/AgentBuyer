"""Vistas de solo lectura para el trail de auditoría append-only."""

from fastapi import APIRouter

from audit.log import get_trail_for


router = APIRouter()


@router.get("/audit")
def get_audit_trail():
    """Devuelve el trail completo para la vista de auditoría."""
    return get_trail_for("auditor")


@router.get("/audit/{mandate_id}")
def get_mandate_audit_trail(mandate_id: str):
    """Devuelve los eventos visibles para el humano dueño de un mandato."""
    return get_trail_for("human", mandate_id)
