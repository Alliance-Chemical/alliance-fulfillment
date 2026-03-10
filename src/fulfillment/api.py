from datetime import datetime, timezone
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from fulfillment.db import FulfillmentDB
from fulfillment.sms import SMSNotifier
from fulfillment.config import config


def create_app(db: FulfillmentDB | None = None, sms: SMSNotifier | None = None) -> FastAPI:
    app = FastAPI(title="Alliance Fulfillment Queue")
    db = db or FulfillmentDB(config.db_path)
    sms = sms or SMSNotifier(
        account_sid=config.twilio_account_sid,
        auth_token=config.twilio_auth_token,
        from_number=config.twilio_from_number,
    )

    templates_dir = Path(__file__).parent / "templates"
    if templates_dir.exists():
        templates = Jinja2Templates(directory=str(templates_dir))
    else:
        templates = None

    # --- Health ---

    @app.get("/health")
    async def health():
        stats = db.get_queue_stats()
        return {"status": "ok", "queue": stats}

    # --- Queue API ---

    @app.get("/api/queue/stats")
    async def queue_stats():
        return db.get_queue_stats()

    @app.get("/api/queue/problems")
    async def queue_problems():
        problems = db.get_problem_orders()
        return [p.model_dump(mode="json") for p in problems]

    # --- Picker API ---

    @app.get("/api/pickers")
    async def list_pickers():
        pickers = db.get_all_pickers()
        for p in pickers:
            stats = db.get_picker_stats(p["id"])
            p.update(stats)
        return pickers

    @app.post("/api/pickers")
    async def register_picker(request: Request):
        body = await request.json()
        name = body["name"]
        picker_id = db.create_picker(name)
        picker = db.get_picker(picker_id)
        return picker

    @app.post("/api/pickers/{picker_id}/batch")
    async def request_batch(picker_id: int):
        batch_size = int(db.get_setting("batch_size", str(config.default_batch_size)))
        orders = db.assign_batch(picker_id, batch_size=batch_size)
        return {"orders": [o.model_dump(mode="json") for o in orders]}

    @app.get("/api/pickers/{picker_id}/orders")
    async def picker_orders(picker_id: int):
        orders = db.get_assigned_orders(picker_id)
        return [o.model_dump(mode="json") for o in orders]

    # --- Order Actions ---

    @app.post("/api/orders/{order_id}/complete")
    async def complete_order(order_id: int, request: Request):
        body = await request.json()
        picker_id = body["picker_id"]
        db.complete_order(order_id, picker_id)
        return {"status": "completed"}

    @app.post("/api/orders/{order_id}/problem")
    async def flag_problem(order_id: int, request: Request):
        body = await request.json()
        picker_id = body["picker_id"]
        reason = body["reason"]
        db.flag_problem(order_id, picker_id, reason)
        return {"status": "flagged"}

    # --- Stock Alerts ---

    @app.post("/api/alerts/stock")
    async def create_stock_alert(request: Request):
        body = await request.json()
        picker_id = body["picker_id"]
        product_name = body["product_name"]
        product_sku = body.get("product_sku", "")
        alert_id = db.create_stock_alert(picker_id, product_name, product_sku)

        # Send SMS
        sms_number = db.get_setting("sms_number", "")
        if sms_number:
            picker = db.get_picker(picker_id)
            picker_name = picker["name"] if picker else "Unknown"
            now_str = datetime.now(timezone.utc).strftime("%I:%M %p")
            message = sms.format_low_stock_message(product_name, picker_name, now_str)
            sent = sms.send_sms(sms_number, message)
            if sent:
                db.mark_alert_sent(alert_id)

        return {"alert_id": alert_id}

    @app.get("/api/alerts/stock/today")
    async def stock_alerts_today():
        return db.get_stock_alerts_today()

    # --- Settings ---

    @app.get("/api/settings")
    async def get_settings():
        return {
            "batch_size": db.get_setting("batch_size", str(config.default_batch_size)),
            "active_picker_slots": db.get_setting("active_picker_slots", str(config.default_picker_slots)),
            "sms_number": db.get_setting("sms_number", ""),
            "refresh_interval": db.get_setting("refresh_interval", str(config.queue_refresh_seconds)),
        }

    @app.post("/api/settings")
    async def update_setting(request: Request):
        body = await request.json()
        db.set_setting(body["key"], body["value"])
        return {"status": "updated"}

    # --- HTML Dashboards (HTMX) ---

    @app.get("/picker", response_class=HTMLResponse)
    async def picker_dashboard(request: Request):
        if not templates:
            return HTMLResponse("<h1>Templates not found</h1>", status_code=500)
        return templates.TemplateResponse("picker.html", {"request": request})

    @app.get("/manager", response_class=HTMLResponse)
    async def manager_dashboard(request: Request):
        if not templates:
            return HTMLResponse("<h1>Templates not found</h1>", status_code=500)
        return templates.TemplateResponse("manager.html", {"request": request})

    return app


def main():
    import uvicorn
    import asyncio
    from fulfillment.sync import QueueSync
    from fulfillment.queue import QueueEngine
    from fulfillment.shipstation import ShipStationAPI

    db_instance = FulfillmentDB(config.db_path)
    app_instance = create_app(db_instance)

    async def start_sync(db):
        ss_api = ShipStationAPI(api_key=config.shipstation_api_key, api_secret=config.shipstation_api_secret)
        engine = QueueEngine()
        sync = QueueSync(db=db, ss_api=ss_api, engine=engine)
        interval = int(db.get_setting("refresh_interval", str(config.queue_refresh_seconds)))
        await sync.run_loop(interval_seconds=interval)

    uv_config = uvicorn.Config(app_instance, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(uv_config)

    async def run():
        sync_task = asyncio.create_task(start_sync(db_instance))
        await server.serve()
        sync_task.cancel()

    asyncio.run(run())
