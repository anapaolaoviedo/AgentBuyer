"""Integración del descubrimiento real: /merchant/search y /agent/run con
search_fields. La red SIEMPRE va mockeada (se parcha _call_web_search)."""
import json

import pytest
from fastapi.testclient import TestClient

from api.main import app
from audit.log import AUDIT_TRAIL
from core import mandate_store, merchant_search

WEB_OFFERS = [
    {"merchant": "Despegar", "price": 55.95, "currency": "USD",
     "details": "Aeromexico NLU-CUN directo", "url": "https://despegar.example/1"},
    {"merchant": "Kayak", "price": 54.71, "currency": "USD",
     "details": "Aeromexico MEX-CUN 22:00", "url": "https://kayak.example/2"},
]

SEARCH_FIELDS = {"origin": "MEX", "destination": "CUN", "departure_date": "2026-09-15"}


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        mandate_store.MANDATES.clear()
        AUDIT_TRAIL.clear()
        yield test_client
    mandate_store.MANDATES.clear()
    AUDIT_TRAIL.clear()


def web_mandate(allowed_merchants: list[str]) -> dict:
    return {
        "mandate_id": "mnd_web_001",
        "human": {"id": "hum_test", "name": "Test"},
        "agent": {"id": "agt_test"},
        "constraints": {
            "max_amount_per_purchase": 150.00,
            "allowed_categories": ["travel.flights"],
            "allowed_merchants": allowed_merchants,
            "max_uses": 3,
            "conditions": [{"type": "price_below", "value": 150.00}],
        },
        "signature": "firma-de-prueba",
    }


def test_merchant_search_endpoint_returns_offers(client, monkeypatch):
    monkeypatch.setattr(merchant_search, "_call_web_search", lambda p: json.dumps(WEB_OFFERS))
    response = client.post("/merchant/search", json={"category": "flights", "fields": SEARCH_FIELDS})
    assert response.status_code == 200
    offers = response.json()
    assert len(offers) == 2 and offers[0]["merchant"] == "Despegar"


def test_merchant_search_endpoint_validates_body(client):
    assert client.post("/merchant/search", json={"category": "yates", "fields": {}}).status_code == 422
    assert client.post("/merchant/search", json={"category": "flights", "fields": "x"}).status_code == 422
    assert client.post(
        "/merchant/search", json={"category": "flights", "fields": SEARCH_FIELDS, "max_results": 99}
    ).status_code == 422


def test_agent_run_uses_web_offers_when_search_fields_present(client, monkeypatch):
    monkeypatch.setattr(merchant_search, "_call_web_search", lambda p: json.dumps(WEB_OFFERS))
    client.post("/mandates", json=web_mandate(["mch_despegar", "mch_kayak"]))

    result = client.post(
        "/agent/run", json={"mandate_id": "mnd_web_001", "search_fields": SEARCH_FIELDS}
    ).json()

    assert result["discovery_source"] == "web"
    assert result["purchase_completed"] is True
    # Eligió la más barata de las ofertas web reales, no del catálogo mock.
    assert result["selected_flight"]["merchant_id"] == "mch_kayak"
    assert result["selected_flight"]["price"] == 54.71
    assert result["attempt"]["purchase"]["metadata"]["source"] == "web"


def test_agent_run_falls_back_to_mock_when_search_fails(client, monkeypatch):
    def broken(prompt):
        raise RuntimeError("sin red")

    monkeypatch.setattr(merchant_search, "_call_web_search", broken)
    client.post("/mandates", json=web_mandate(["mch_vuelaya"]))

    result = client.post(
        "/agent/run", json={"mandate_id": "mnd_web_001", "search_fields": SEARCH_FIELDS}
    ).json()

    assert result["discovery_source"] == "mock"
    assert result["selected_flight"]["merchant_id"] == "mch_vuelaya"
    assert result["purchase_completed"] is True


def test_agent_run_without_search_fields_keeps_old_behavior(client):
    client.post("/mandates", json=web_mandate(["mch_vuelaya"]))
    result = client.post("/agent/run", json={"mandate_id": "mnd_web_001"}).json()
    assert result["discovery_source"] == "mock"
    assert result["selected_flight"]["merchant_id"] == "mch_vuelaya"
