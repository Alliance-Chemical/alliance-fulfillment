from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field


class AgeBracket(str, Enum):
    GREEN = "green"
    ORANGE = "orange"
    YELLOW = "yellow"
    RED = "red"

    @classmethod
    def from_hours(cls, hours: float) -> AgeBracket:
        if hours >= 72:
            return cls.RED
        if hours >= 48:
            return cls.YELLOW
        if hours >= 24:
            return cls.ORANGE
        return cls.GREEN


class OrderZone(str, Enum):
    QUART = "quart"
    GALLON = "gallon"
    CASE = "case"
    OTHER = "other"

    @classmethod
    def from_options(cls, option1: str, option2: str) -> OrderZone:
        o1 = option1.lower().strip()
        o2 = option2.lower().strip()
        if "quart" in o1 or "pint" in o1:
            return cls.QUART
        if "gallon" in o1:
            if "x" in o2 or "case" in o2:
                return cls.CASE
            return cls.GALLON
        return cls.OTHER


class LineItem(BaseModel):
    sku: str | None = None
    name: str | None = None
    quantity: int = 1
    unit_price: float | None = None
    option1: str | None = None
    option2: str | None = None


class QueuedOrder(BaseModel):
    id: int | None = None
    shipstation_order_id: int
    order_number: str
    order_date: datetime
    age_hours: float = 0.0
    age_bracket: AgeBracket = AgeBracket.GREEN
    priority_score: float = 0.0
    zone: OrderZone = OrderZone.OTHER
    line_items: list[LineItem] = []
    customer_name: str = ""
    ship_to_state: str = ""
    order_value: float = 0.0
    assigned_to_picker: int | None = None
    assigned_at: datetime | None = None
    status: str = "queued"
    problem_reason: str | None = None
    has_priority_tag: bool = False
    tag_ids: list[int] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Picker(BaseModel):
    id: int | None = None
    name: str
    status: str = "idle"
    current_batch_id: int | None = None
    orders_completed_today: int = 0
    avg_time_per_order: float = 0.0


class Batch(BaseModel):
    id: int | None = None
    picker_id: int
    order_ids: list[int] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    status: str = "active"

    @property
    def order_count(self) -> int:
        return len(self.order_ids)


class StockAlert(BaseModel):
    id: int | None = None
    picker_id: int
    picker_name: str = ""
    product_name: str
    product_sku: str = ""
    flagged_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sms_sent: bool = False


class QueueSettings(BaseModel):
    batch_size: int = 8
    active_picker_slots: int = 5
    refresh_interval_seconds: int = 120
    sms_number: str = ""
