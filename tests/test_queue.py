import pytest
from datetime import datetime, timezone, timedelta
from fulfillment.queue import QueueEngine
from fulfillment.models import AgeBracket, OrderZone, LineItem

# Tag IDs from ShipStation
HOT_SHIPMENT = 48500
PICK_PACK_TODAY = 57205
AMAZON_PRIME = 44791
FREIGHT = 19844
HAZMAT = 44198


def make_ss_order(order_id, order_number, order_date, items=None, tag_ids=None, amount_paid=10.0):
    """Build a dict mimicking ShipStation API order response."""
    return {
        "orderId": order_id,
        "orderNumber": order_number,
        "orderDate": order_date.isoformat(),
        "orderStatus": "awaiting_shipment",
        "shipTo": {"name": "Test Customer", "state": "TX", "city": "Houston", "postalCode": "77001", "country": "US"},
        "items": items or [{"sku": "IPA-1GAL", "name": "Isopropyl Alcohol - 1 Gallon / 1 Gallon", "quantity": 1, "unitPrice": 10.0}],
        "tagIds": tag_ids or [],
        "amountPaid": amount_paid,
    }


class TestQueueEngine:
    def setup_method(self):
        self.engine = QueueEngine()
        self.now = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)

    def test_filters_out_tagged_orders(self):
        orders = [
            make_ss_order(1, "1001", self.now - timedelta(hours=1)),
            make_ss_order(2, "1002", self.now - timedelta(hours=1), tag_ids=[FREIGHT]),
            make_ss_order(3, "1003", self.now - timedelta(hours=1), tag_ids=[HAZMAT]),
        ]
        result = self.engine.process_orders(orders, now=self.now)
        assert len(result) == 1
        assert result[0].order_number == "1001"

    def test_keeps_hot_shipment_and_prime_tags(self):
        orders = [
            make_ss_order(1, "1001", self.now - timedelta(hours=1), tag_ids=[HOT_SHIPMENT]),
            make_ss_order(2, "1002", self.now - timedelta(hours=1), tag_ids=[AMAZON_PRIME]),
        ]
        result = self.engine.process_orders(orders, now=self.now)
        assert len(result) == 2

    def test_hot_shipment_beats_old_age(self):
        orders = [
            make_ss_order(1, "OLD", self.now - timedelta(hours=96)),
            make_ss_order(2, "HOT", self.now - timedelta(hours=1), tag_ids=[HOT_SHIPMENT]),
        ]
        result = self.engine.process_orders(orders, now=self.now)
        assert result[0].order_number == "HOT"
        assert result[1].order_number == "OLD"

    def test_amazon_prime_beats_old_age(self):
        orders = [
            make_ss_order(1, "OLD", self.now - timedelta(hours=96)),
            make_ss_order(2, "PRIME", self.now - timedelta(hours=1), tag_ids=[AMAZON_PRIME]),
        ]
        result = self.engine.process_orders(orders, now=self.now)
        assert result[0].order_number == "PRIME"

    def test_age_brackets_sorted_correctly(self):
        orders = [
            make_ss_order(1, "FRESH", self.now - timedelta(hours=2)),
            make_ss_order(2, "OLD3", self.now - timedelta(hours=73)),
            make_ss_order(3, "OLD2", self.now - timedelta(hours=49)),
            make_ss_order(4, "OLD1", self.now - timedelta(hours=25)),
        ]
        result = self.engine.process_orders(orders, now=self.now)
        assert [o.order_number for o in result] == ["OLD3", "OLD2", "OLD1", "FRESH"]

    def test_same_age_bracket_grouped_by_zone(self):
        base = self.now - timedelta(hours=80)
        orders = [
            make_ss_order(1, "GAL1", base, items=[{"sku": "A", "name": "Product - 1 Gallon / 1 Gallon", "quantity": 1}]),
            make_ss_order(2, "QT1", base, items=[{"sku": "B", "name": "Product - 1 Quart / 1 Quart", "quantity": 1}]),
            make_ss_order(3, "GAL2", base, items=[{"sku": "C", "name": "Product - 1 Gallon / 1 Gallon", "quantity": 1}]),
            make_ss_order(4, "QT2", base, items=[{"sku": "D", "name": "Product - 1 Quart / 1 Quart", "quantity": 1}]),
        ]
        result = self.engine.process_orders(orders, now=self.now)
        numbers = [o.order_number for o in result]
        gal_positions = [i for i, n in enumerate(numbers) if n.startswith("GAL")]
        qt_positions = [i for i, n in enumerate(numbers) if n.startswith("QT")]
        assert abs(gal_positions[0] - gal_positions[1]) == 1
        assert abs(qt_positions[0] - qt_positions[1]) == 1

    def test_tiebreaker_higher_value_first(self):
        base = self.now - timedelta(hours=25)
        orders = [
            make_ss_order(1, "CHEAP", base, amount_paid=10.0,
                          items=[{"sku": "A", "name": "P - 1 Gallon / 1 Gallon", "quantity": 1}]),
            make_ss_order(2, "EXPENSIVE", base, amount_paid=100.0,
                          items=[{"sku": "B", "name": "P - 1 Gallon / 1 Gallon", "quantity": 1}]),
        ]
        result = self.engine.process_orders(orders, now=self.now)
        assert result[0].order_number == "EXPENSIVE"

    def test_zone_detection_from_item_name(self):
        zone = self.engine._detect_zone_from_items([
            {"sku": "A", "name": "Isopropyl Alcohol - 1 Gallon / 4 x 1 Gallon", "quantity": 1}
        ])
        assert zone == OrderZone.CASE

    def test_mixed_zone_order_detected(self):
        zones = self.engine._detect_zones_from_items([
            {"sku": "A", "name": "Product A - 1 Quart / 1 Quart", "quantity": 1},
            {"sku": "B", "name": "Product B - 1 Gallon / 1 Gallon", "quantity": 1},
        ])
        assert OrderZone.QUART in zones
        assert OrderZone.GALLON in zones
