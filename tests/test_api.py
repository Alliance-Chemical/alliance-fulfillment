import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from fulfillment.api import create_app
from fulfillment.db import FulfillmentDB
from fulfillment.models import QueuedOrder, AgeBracket, OrderZone, LineItem


@pytest.fixture
def db(tmp_path):
    return FulfillmentDB(str(tmp_path / "test.db"))


@pytest.fixture
def client(db):
    app = create_app(db)
    return TestClient(app)


@pytest.fixture
def seeded_db(db):
    for i in range(3):
        db.upsert_order(QueuedOrder(
            shipstation_order_id=100 + i,
            order_number=f"100{i}",
            order_date=datetime(2026, 3, 7, tzinfo=timezone.utc),
            age_hours=72.0 - i * 24,
            age_bracket=[AgeBracket.RED, AgeBracket.YELLOW, AgeBracket.GREEN][i],
            priority_score=1000 - i * 100,
            zone=OrderZone.GALLON,
            line_items=[LineItem(sku=f"SKU{i}", name=f"Product {i}", quantity=1)],
            customer_name=f"Customer {i}",
            ship_to_state="TX",
            order_value=10.0 + i * 5,
        ))
    db.create_picker("Maria")
    return db


@pytest.fixture
def seeded_client(seeded_db):
    app = create_app(seeded_db)
    return TestClient(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_get_queue_stats(seeded_client):
    resp = seeded_client.get("/api/queue/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3


def test_register_picker(client):
    resp = client.post("/api/pickers", json={"name": "Maria"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Maria"


def test_request_batch(seeded_client):
    resp = seeded_client.post("/api/pickers/1/batch")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["orders"]) == 3


def test_complete_order(seeded_client):
    seeded_client.post("/api/pickers/1/batch")
    resp = seeded_client.post("/api/orders/1/complete", json={"picker_id": 1})
    assert resp.status_code == 200
    stats = seeded_client.get("/api/queue/stats").json()
    assert stats["completed_today"] >= 1


def test_flag_problem(seeded_client):
    seeded_client.post("/api/pickers/1/batch")
    resp = seeded_client.post("/api/orders/1/problem", json={"picker_id": 1, "reason": "Out of stock"})
    assert resp.status_code == 200
    problems = seeded_client.get("/api/queue/problems").json()
    assert len(problems) == 1


def test_create_stock_alert(seeded_client):
    resp = seeded_client.post("/api/alerts/stock", json={
        "picker_id": 1,
        "product_name": "Isopropyl Alcohol 1 Gal",
        "product_sku": "IPA-1GAL",
    })
    assert resp.status_code == 200
    alerts = seeded_client.get("/api/alerts/stock/today").json()
    assert len(alerts) == 1


def test_get_and_set_settings(client):
    resp = client.post("/api/settings", json={"key": "batch_size", "value": "10"})
    assert resp.status_code == 200
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["batch_size"] == "10"


def test_get_pickers(seeded_client):
    resp = seeded_client.get("/api/pickers")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "Maria"
