import pytest
from datetime import datetime, timezone, timedelta
from fulfillment.models import (
    QueuedOrder, Picker, Batch, StockAlert, AgeBracket, OrderZone,
    QueueSettings, LineItem,
)


def test_age_bracket_from_hours():
    assert AgeBracket.from_hours(0.5) == AgeBracket.GREEN
    assert AgeBracket.from_hours(12) == AgeBracket.GREEN
    assert AgeBracket.from_hours(25) == AgeBracket.ORANGE
    assert AgeBracket.from_hours(49) == AgeBracket.YELLOW
    assert AgeBracket.from_hours(73) == AgeBracket.RED


def test_order_zone_from_options():
    assert OrderZone.from_options("1 Quart", "1 Quart") == OrderZone.QUART
    assert OrderZone.from_options("1 Gallon", "1 Gallon") == OrderZone.GALLON
    assert OrderZone.from_options("1 Gallon", "4 x 1 Gallon") == OrderZone.CASE
    assert OrderZone.from_options("unknown", "unknown") == OrderZone.OTHER


def test_queued_order_creation():
    order = QueuedOrder(
        shipstation_order_id=123,
        order_number="1001",
        order_date=datetime(2026, 3, 7, 12, 0, tzinfo=timezone.utc),
        age_hours=72.0,
        age_bracket=AgeBracket.RED,
        priority_score=1000,
        zone=OrderZone.GALLON,
        line_items=[LineItem(sku="IPA-1GAL", name="Isopropyl Alcohol 1 Gallon", quantity=2, unit_price=15.99, option1="1 Gallon", option2="1 Gallon")],
        customer_name="John Smith",
        ship_to_state="TX",
        order_value=31.98,
    )
    assert order.status == "queued"
    assert order.assigned_to_picker is None


def test_picker_creation():
    picker = Picker(name="Maria")
    assert picker.status == "idle"
    assert picker.orders_completed_today == 0


def test_batch_creation():
    batch = Batch(picker_id=1, order_ids=[101, 102, 103])
    assert batch.status == "active"
    assert batch.order_count == 3


def test_queue_settings_defaults():
    settings = QueueSettings()
    assert settings.batch_size == 8
    assert settings.active_picker_slots == 5
    assert settings.refresh_interval_seconds == 120
    assert settings.sms_number == ""
