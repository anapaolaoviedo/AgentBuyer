"""API del comercio mock VuelaYa."""

from fastapi import APIRouter

from core.merchant import get_flights


router = APIRouter()


@router.get("/merchant/flights")
def list_flights():
    """Devuelve el catálogo actual de vuelos inventados de VuelaYa."""
    return get_flights()
