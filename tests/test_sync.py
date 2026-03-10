import pytest
import httpx
import respx
from datetime import datetime, timezone, timedelta
from fulfillment.sync import QueueSync
from fulfillment.db import FulfillmentDB
from fulfillment.queue import QueueEngine
from fulfillment.shipstation import ShipStationAPI


@pytest.fixture
def db(tmp_path):
    return FulfillmentDB(str(tmp_path / "test.db"))


@pytest.fixture
def ss_api():
    return ShipStationAPI(api_key="test", api_secret="test")


@pytest.fixture
def sync(db, ss_api):
    return QueueSync(db=db, ss_api=ss_api, engine=QueueEngine())


def make_ss_response(orders):
    return {"orders": orders, "total": len(orders), "page": 1, "pages": 1}


@respx.mock
@pytest.mark.asyncio
async def test_sync_pulls_and_scores_orders(sync, db):
    now = datetime.now(timezone.utc)
    respx.get("https://ssapi.shipstation.com/orders").mock(
        return_value=httpx.Response(200, json=make_ss_response([
            {
                "orderId": 1, "orderNumber": "1001",
                "orderDate": (now - timedelta(hours=50)).isoformat(),
                "orderStatus": "awaiting_shipment",
                "shipTo": {"name": "John", "state": "TX", "city": "Houston", "postalCode": "77001", "country": "US"},
                "items": [{"sku": "IPA-1GAL", "name": "IPA - 1 Gallon / 1 Gallon", "quantity": 1, "unitPrice": 10.0}],
                "tagIds": [],
                "amountPaid": 10.0,
            },
            {
                "orderId": 2, "orderNumber": "1002",
                "orderDate": (now - timedelta(hours=2)).isoformat(),
                "orderStatus": "awaiting_shipment",
                "shipTo": {"name": "Jane", "state": "CA", "city": "LA", "postalCode": "90001", "country": "US"},
                "items": [{"sku": "ACE-1QT", "name": "Acetone - 1 Quart / 1 Quart", "quantity": 2, "unitPrice": 8.0}],
                "tagIds": [],
                "amountPaid": 16.0,
            },
        ]))
    )
    await sync.sync_once()
    orders = db.get_queued_orders()
    assert len(orders) == 2
    assert orders[0].order_number == "1001"


@respx.mock
@pytest.mark.asyncio
async def test_sync_removes_shipped_orders(sync, db):
    now = datetime.now(timezone.utc)
    respx.get("https://ssapi.shipstation.com/orders").mock(
        return_value=httpx.Response(200, json=make_ss_response([
            {
                "orderId": 1, "orderNumber": "1001",
                "orderDate": (now - timedelta(hours=2)).isoformat(),
                "orderStatus": "awaiting_shipment",
                "shipTo": {"name": "John", "state": "TX", "city": "Houston", "postalCode": "77001", "country": "US"},
                "items": [{"sku": "A", "name": "P - 1 Gallon / 1 Gallon", "quantity": 1}],
                "tagIds": [], "amountPaid": 10.0,
            },
        ]))
    )
    await sync.sync_once()
    orders = db.get_queued_orders()
    assert len(orders) == 1

    respx.get("https://ssapi.shipstation.com/orders").mock(
        return_value=httpx.Response(200, json=make_ss_response([
            {
                "orderId": 3, "orderNumber": "1003",
                "orderDate": now.isoformat(),
                "orderStatus": "awaiting_shipment",
                "shipTo": {"name": "Bob", "state": "FL", "city": "Miami", "postalCode": "33101", "country": "US"},
                "items": [{"sku": "B", "name": "P - 1 Quart / 1 Quart", "quantity": 1}],
                "tagIds": [], "amountPaid": 5.0,
            },
        ]))
    )
    await sync.sync_once()
    orders = db.get_queued_orders()
    assert len(orders) == 1
    assert orders[0].order_number == "1003"
