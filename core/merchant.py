"""Catálogo en memoria del comercio mock VuelaYa."""

from copy import deepcopy


FLIGHTS: list[dict] = [
    {"id": "fly_vy_001", "route": "BUE->COR", "price": 130.0, "category": "travel.flights", "merchant_id": "mch_vuelaya"},
    {"id": "fly_vy_002", "route": "BUE->COR", "price": 145.0, "category": "travel.flights", "merchant_id": "mch_vuelaya"},
    {"id": "fly_vy_003", "route": "BUE->MDZ", "price": 210.0, "category": "travel.flights", "merchant_id": "mch_vuelaya"},
    {"id": "fly_vy_004", "route": "BUE->SCL", "price": 300.0, "category": "travel.flights", "merchant_id": "mch_vuelaya"},
    {"id": "fly_vy_005", "route": "BUE->SAL", "price": 175.0, "category": "travel.flights", "merchant_id": "mch_vuelaya"},
]


def get_flights() -> list[dict]:
    """Entrega una copia para que ningún cliente cambie el catálogo interno."""
    return deepcopy(FLIGHTS)
