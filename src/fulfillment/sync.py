import asyncio
import logging
from fulfillment.db import FulfillmentDB
from fulfillment.queue import QueueEngine
from fulfillment.shipstation import ShipStationAPI

logger = logging.getLogger(__name__)


class QueueSync:
    def __init__(self, db: FulfillmentDB, ss_api: ShipStationAPI, engine: QueueEngine):
        self.db = db
        self.ss_api = ss_api
        self.engine = engine

    async def sync_once(self):
        all_raw_orders = []
        page = 1
        while True:
            result = await self.ss_api.list_orders(
                status="awaiting_shipment", page=page, page_size=100
            )
            for order in result["orders"]:
                all_raw_orders.append(order.model_dump())
            if page >= result["pages"]:
                break
            page += 1

        scored = self.engine.process_orders(all_raw_orders)

        active_ids = set()
        for order in scored:
            self.db.upsert_order(order)
            active_ids.add(order.shipstation_order_id)

        self.db.remove_shipped_orders(active_ids)
        logger.info(f"Queue sync complete: {len(scored)} orders in queue")

    async def run_loop(self, interval_seconds: int = 120):
        while True:
            try:
                await self.sync_once()
            except Exception as e:
                logger.error(f"Queue sync error: {e}")
            await asyncio.sleep(interval_seconds)
