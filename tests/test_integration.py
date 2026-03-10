"""End-to-end smoke test: ShipStation orders -> queue -> picker batch -> complete."""
import pytest
import httpx
import respx
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from fulfillment.api import create_app
from fulfillment.db import FulfillmentDB
from fulfillment.queue import QueueEngine
from fulfillment.sync import QueueSync
from fulfillment.shipstation import ShipStationAPI


@pytest.fixture
def db(tmp_path):
    return FulfillmentDB(str(tmp_path / "integration.db"))


@pytest.fixture
def ss_api():
    return ShipStationAPI(api_key="test", api_secret="test")


@pytest.fixture
def client(db):
    app = create_app(db)
    return TestClient(app)


@respx.mock
@pytest.mark.asyncio
async def test_full_workflow(db, ss_api, client):
    now = datetime.now(timezone.utc)
    engine = QueueEngine()
    sync = QueueSync(db=db, ss_api=ss_api, engine=engine)

    ages = [80, 50, 25, 5, 1]
    item_names = [
        "IPA - 1 Quart / 1 Quart",
        "Acetone - 1 Gallon / 1 Gallon",
        "MEK - 1 Gallon / 4 x 1 Gallon",
        "NaOH - 1 Quart / 1 Quart",
        "HCl - 1 Gallon / 1 Gallon",
    ]

    # 1. Mock ShipStation with 5 orders of varying ages and zones
    respx.get("https://ssapi.shipstation.com/orders").mock(
        return_value=httpx.Response(200, json={
            "orders": [
                {
                    "orderId": i, "orderNumber": f"100{i}",
                    "orderDate": (now - timedelta(hours=ages[i])).isoformat(),
                    "orderStatus": "awaiting_shipment",
                    "shipTo": {"name": f"Customer {i}", "state": "TX",
                               "city": "Houston", "postalCode": "77001",
                               "country": "US"},
                    "items": [{"sku": f"SKU{i}", "name": item_names[i],
                               "quantity": 1, "unitPrice": 10.0 + i * 5}],
                    "tagIds": [],
                    "amountPaid": 10.0 + i * 5,
                }
                for i in range(5)
            ],
            "total": 5, "page": 1, "pages": 1,
        })
    )

    # 2. Sync orders from ShipStation into fulfillment queue
    await sync.sync_once()

    # 3. Verify queue stats — all 5 orders should be queued
    stats = client.get("/api/queue/stats").json()
    assert stats["total"] == 5

    # 4. Register picker
    picker = client.post("/api/pickers", json={"name": "Maria"}).json()
    picker_id = picker["id"]

    # 5. Request batch — should get all 5 orders sorted by priority
    batch = client.post(f"/api/pickers/{picker_id}/batch").json()
    assert len(batch["orders"]) == 5
    # First order should be the oldest (80h, RED bracket, order 1000)
    assert batch["orders"][0]["order_number"] == "1000"

    # 6. Complete first 3 orders
    for order in batch["orders"][:3]:
        resp = client.post(f"/api/orders/{order['id']}/complete",
                           json={"picker_id": picker_id})
        assert resp.status_code == 200

    # 7. Flag problem on 4th order
    resp = client.post(f"/api/orders/{batch['orders'][3]['id']}/problem",
                       json={"picker_id": picker_id, "reason": "Damaged"})
    assert resp.status_code == 200

    # 8. Verify final state — 1 still assigned, 3 completed, 1 problem
    stats = client.get("/api/queue/stats").json()
    assert stats["completed_today"] == 3
    assert stats["problems"] == 1
    # Only 1 order remains in active queue (assigned but not completed/problem)
    assert stats["total"] == 1

    problems = client.get("/api/queue/problems").json()
    assert len(problems) == 1
    assert problems[0]["problem_reason"] == "Damaged"
