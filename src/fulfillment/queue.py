from datetime import datetime, timezone
from fulfillment.models import (
    QueuedOrder, AgeBracket, OrderZone, LineItem,
)

# ShipStation tag IDs
HOT_SHIPMENT_TAG = 48500
PICK_PACK_TODAY_TAG = 57205
AMAZON_PRIME_TAG = 44791

# Tags that mean "this order belongs to another workflow"
EXCLUDED_TAG_IDS = {
    19844,   # Freight Orders
    44123,   # Freight Order Ready
    44198,   # Hazmat Orders
    47435,   # International Orders
    49499,   # Back Order
    44125,   # Customer Pick Up
    44126,   # Local Customer Order
    44124,   # SAIC/GOV/AMENTUM Order
    46283,   # Delay Shipment/Don't Ship
    51273,   # Documents / Certificates Required
    44777,   # Need Labels
    44744,   # No Inventory
    54309,   # UMS
}

# Tags that ARE allowed (priority boosters, not exclusions)
PRIORITY_TAG_IDS = {HOT_SHIPMENT_TAG, PICK_PACK_TODAY_TAG, AMAZON_PRIME_TAG}

# Zone sort order for batching within same age bracket
ZONE_SORT_ORDER = {
    OrderZone.QUART: 0,
    OrderZone.GALLON: 1,
    OrderZone.CASE: 2,
    OrderZone.OTHER: 3,
}


class QueueEngine:
    def process_orders(
        self, raw_orders: list[dict], now: datetime | None = None
    ) -> list[QueuedOrder]:
        now = now or datetime.now(timezone.utc)
        scored = []
        for raw in raw_orders:
            order = self._parse_and_score(raw, now)
            if order is not None:
                scored.append(order)
        return self._sort_orders(scored)

    def _parse_and_score(self, raw: dict, now: datetime) -> QueuedOrder | None:
        tag_ids = raw.get("tagIds") or []

        # Filter out orders that belong to other workflows
        has_excluded = any(t in EXCLUDED_TAG_IDS for t in tag_ids)
        if has_excluded:
            return None

        order_date_str = raw.get("orderDate", "")
        try:
            order_date = datetime.fromisoformat(order_date_str.replace("Z", "+00:00"))
            if order_date.tzinfo is None:
                order_date = order_date.replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError):
            order_date = now

        age_hours = (now - order_date).total_seconds() / 3600
        age_bracket = AgeBracket.from_hours(age_hours)

        items = raw.get("items") or []
        zone = self._detect_zone_from_items(items)

        has_priority = any(t in PRIORITY_TAG_IDS for t in tag_ids)
        has_hot = HOT_SHIPMENT_TAG in tag_ids or PICK_PACK_TODAY_TAG in tag_ids
        has_prime = AMAZON_PRIME_TAG in tag_ids

        order_value = float(raw.get("amountPaid") or 0)
        order_number = raw.get("orderNumber", "")

        # Score: higher = higher priority
        # Tier 1: priority tags (10000+ range)
        # Tier 2: age bracket (1000-9999 range)
        # Tier 3: zone grouping (handled in sort, not score)
        # Tier 5: tiebreaker by value and order number
        score = 0.0

        if has_hot:
            score += 20000
        elif has_prime:
            score += 10000

        bracket_scores = {
            AgeBracket.RED: 4000,
            AgeBracket.YELLOW: 3000,
            AgeBracket.ORANGE: 2000,
            AgeBracket.GREEN: 1000,
        }
        score += bracket_scores[age_bracket]

        # Value tiebreaker (0-999 range, normalized)
        score += min(order_value, 999)

        ship_to = raw.get("shipTo") or {}
        line_items = []
        for item in items:
            name = item.get("name", "")
            o1, o2 = self._parse_options_from_name(name)
            line_items.append(LineItem(
                sku=item.get("sku"),
                name=name,
                quantity=item.get("quantity", 1),
                unit_price=item.get("unitPrice"),
                option1=o1,
                option2=o2,
            ))

        return QueuedOrder(
            shipstation_order_id=raw["orderId"],
            order_number=order_number,
            order_date=order_date,
            age_hours=age_hours,
            age_bracket=age_bracket,
            priority_score=score,
            zone=zone,
            line_items=line_items,
            customer_name=ship_to.get("name", ""),
            ship_to_state=ship_to.get("state", ""),
            order_value=order_value,
            has_priority_tag=has_priority,
            tag_ids=tag_ids,
        )

    def _sort_orders(self, orders: list[QueuedOrder]) -> list[QueuedOrder]:
        """Sort by priority score DESC, then group by zone within same bracket."""
        # First pass: group by (priority_tier, age_bracket)
        groups: dict[tuple, list[QueuedOrder]] = {}
        for order in orders:
            tier = "hot" if order.priority_score >= 20000 else \
                   "prime" if order.priority_score >= 10000 else "normal"
            key = (tier, order.age_bracket.value)
            groups.setdefault(key, []).append(order)

        # Within each group, sort by zone then by value DESC
        tier_order = {"hot": 0, "prime": 1, "normal": 2}
        bracket_order = {"red": 0, "yellow": 1, "orange": 2, "green": 3}

        sorted_keys = sorted(
            groups.keys(),
            key=lambda k: (tier_order.get(k[0], 9), bracket_order.get(k[1], 9))
        )

        result = []
        for key in sorted_keys:
            group = groups[key]
            group.sort(key=lambda o: (
                ZONE_SORT_ORDER.get(o.zone, 99),
                -o.order_value,
                o.order_number,
            ))
            result.extend(group)

        return result

    def _detect_zone_from_items(self, items: list[dict]) -> OrderZone:
        zones = self._detect_zones_from_items(items)
        if not zones:
            return OrderZone.OTHER
        # Primary zone = first in priority order
        for z in [OrderZone.QUART, OrderZone.GALLON, OrderZone.CASE]:
            if z in zones:
                return z
        return OrderZone.OTHER

    def _detect_zones_from_items(self, items: list[dict]) -> set[OrderZone]:
        zones = set()
        for item in items:
            name = item.get("name", "")
            o1, o2 = self._parse_options_from_name(name)
            zone = OrderZone.from_options(o1, o2)
            zones.add(zone)
        return zones

    def _parse_options_from_name(self, name: str) -> tuple[str, str]:
        """Parse Option1 / Option2 from ShipStation item name.

        ShipStation item names typically follow the pattern:
        'Product Name - Option1 / Option2'
        e.g. 'Isopropyl Alcohol - 1 Gallon / 4 x 1 Gallon'
        """
        if " - " not in name or " / " not in name:
            return (name, name)
        try:
            _, options_part = name.rsplit(" - ", 1)
            parts = options_part.split(" / ", 1)
            if len(parts) == 2:
                return (parts[0].strip(), parts[1].strip())
            return (parts[0].strip(), parts[0].strip())
        except (ValueError, IndexError):
            return (name, name)
