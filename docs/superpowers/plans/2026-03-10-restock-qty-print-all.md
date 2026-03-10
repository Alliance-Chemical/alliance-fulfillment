# Per-Item Restock Quantities + Print All Slips Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the global "Flag Low Stock" with per-line-item restock quantity inputs on each order card, and replace per-order "Print Slip" buttons with a single "Print All Slips" button for the batch.

**Architecture:** Extend the `stock_alerts` DB table with `restock_qty` and `order_id` columns. Modify the `POST /api/alerts/stock` endpoint to accept these new fields. Update the picker UI to render restock inputs per line item and a batch-level print button. Update the manager dashboard to display restock quantities. Update SMS message format to include quantity and order number.

**Tech Stack:** Python/FastAPI, SQLite, Jinja2 templates, vanilla JavaScript, Twilio SMS

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/fulfillment/db.py` | Modify | Add migration for `restock_qty`/`order_id` columns, update `create_stock_alert` signature |
| `src/fulfillment/sms.py` | Modify | Update SMS message format to include restock qty and order number |
| `src/fulfillment/api.py` | Modify | Update `POST /api/alerts/stock` to accept `restock_qty` and `order_id` |
| `src/fulfillment/templates/picker.html` | Modify | Per-item restock inputs, remove global low stock, remove per-order print, add Print All button |
| `src/fulfillment/templates/manager.html` | Modify | Show restock quantity in alerts display |
| `tests/test_db.py` | Modify | Test new `create_stock_alert` with restock_qty and order_id |
| `tests/test_api.py` | Modify | Test updated stock alert endpoint |
| `tests/test_sms.py` | Modify | Test updated SMS format |

---

## Chunk 1: Backend Changes

### Task 1: Extend stock_alerts table with restock_qty and order_id

**Files:**
- Modify: `src/fulfillment/db.py:72-80` (table creation)
- Modify: `src/fulfillment/db.py:237-243` (create_stock_alert method)
- Modify: `src/fulfillment/db.py:21` (_init_db — add migration)
- Test: `tests/test_db.py`

- [ ] **Step 1: Write failing test for create_stock_alert with restock_qty and order_id**

In `tests/test_db.py`, add after the existing `test_create_stock_alert` (line 107):

```python
def test_create_stock_alert_with_restock_qty(db):
    picker_id = db.create_picker("Maria")
    alert_id = db.create_stock_alert(
        picker_id, "Isopropyl Alcohol 1 Gal", "IPA-1GAL",
        restock_qty=10, order_id=42
    )
    alerts = db.get_stock_alerts_today()
    assert len(alerts) == 1
    assert alerts[0]["product_name"] == "Isopropyl Alcohol 1 Gal"
    assert alerts[0]["restock_qty"] == 10
    assert alerts[0]["order_id"] == 42
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/cruz/alliance-fulfillment && python -m pytest tests/test_db.py::test_create_stock_alert_with_restock_qty -v`
Expected: FAIL — `create_stock_alert()` doesn't accept `restock_qty` or `order_id`

- [ ] **Step 3: Update DB schema and create_stock_alert method**

In `src/fulfillment/db.py`, update the `stock_alerts` table creation (lines 72-80) to add the new columns:

```python
                CREATE TABLE IF NOT EXISTS stock_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    picker_id INTEGER NOT NULL,
                    product_name TEXT NOT NULL,
                    product_sku TEXT DEFAULT '',
                    restock_qty INTEGER DEFAULT 0,
                    order_id INTEGER,
                    flagged_at TEXT NOT NULL DEFAULT (datetime('now')),
                    sms_sent INTEGER DEFAULT 0,
                    FOREIGN KEY (picker_id) REFERENCES pickers(id)
                );
```

After the `_init_db` `executescript` block (after line 86), add a migration to handle existing databases:

```python
            # Migrations for existing databases
            cursor = conn.execute("PRAGMA table_info(stock_alerts)")
            columns = [row[1] for row in cursor.fetchall()]
            if "restock_qty" not in columns:
                conn.execute("ALTER TABLE stock_alerts ADD COLUMN restock_qty INTEGER DEFAULT 0")
            if "order_id" not in columns:
                conn.execute("ALTER TABLE stock_alerts ADD COLUMN order_id INTEGER")
```

Update the `create_stock_alert` method (lines 237-243):

```python
    def create_stock_alert(self, picker_id: int, product_name: str, product_sku: str = "", restock_qty: int = 0, order_id: int | None = None) -> int:
        with self._conn() as conn:
            cursor = conn.execute(
                "INSERT INTO stock_alerts (picker_id, product_name, product_sku, restock_qty, order_id) VALUES (?, ?, ?, ?, ?)",
                (picker_id, product_name, product_sku, restock_qty, order_id)
            )
            return cursor.lastrowid
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/cruz/alliance-fulfillment && python -m pytest tests/test_db.py::test_create_stock_alert_with_restock_qty -v`
Expected: PASS

- [ ] **Step 5: Run all DB tests to check for regressions**

Run: `cd /home/cruz/alliance-fulfillment && python -m pytest tests/test_db.py -v`
Expected: All tests PASS (existing `test_create_stock_alert` still works because new params have defaults)

- [ ] **Step 6: Commit**

```bash
cd /home/cruz/alliance-fulfillment
git add src/fulfillment/db.py tests/test_db.py
git commit -m "feat: add restock_qty and order_id to stock_alerts table"
```

---

### Task 2: Update SMS message format

**Files:**
- Modify: `src/fulfillment/sms.py:24-32` (format_low_stock_message)
- Test: `tests/test_sms.py`

- [ ] **Step 1: Write failing test for updated SMS format**

In `tests/test_sms.py`, add a test (or update existing) for the new message format:

```python
def test_format_restock_message():
    notifier = SMSNotifier("", "", "")
    msg = notifier.format_restock_message(
        product_name="Acetone - 1 Gallon",
        restock_qty=10,
        order_number="1234",
        picker_name="Maria",
        time_str="2:30 PM",
    )
    assert "RESTOCK NEEDED" in msg
    assert "10" in msg
    assert "Acetone - 1 Gallon" in msg
    assert "1234" in msg
    assert "Maria" in msg
    assert "2:30 PM" in msg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/cruz/alliance-fulfillment && python -m pytest tests/test_sms.py::test_format_restock_message -v`
Expected: FAIL — `format_restock_message` doesn't exist

- [ ] **Step 3: Add format_restock_message to SMSNotifier**

In `src/fulfillment/sms.py`, add after the existing `format_low_stock_message` method (after line 32):

```python
    def format_restock_message(
        self, product_name: str, restock_qty: int, order_number: str, picker_name: str, time_str: str
    ) -> str:
        return (
            f"RESTOCK NEEDED\n"
            f"{restock_qty} x {product_name}\n"
            f"Order #{order_number}\n"
            f"Flagged by: {picker_name}\n"
            f"Time: {time_str}"
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/cruz/alliance-fulfillment && python -m pytest tests/test_sms.py::test_format_restock_message -v`
Expected: PASS

- [ ] **Step 5: Run all SMS tests**

Run: `cd /home/cruz/alliance-fulfillment && python -m pytest tests/test_sms.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
cd /home/cruz/alliance-fulfillment
git add src/fulfillment/sms.py tests/test_sms.py
git commit -m "feat: add format_restock_message for per-item restock SMS alerts"
```

---

### Task 3: Update stock alert API endpoint

**Files:**
- Modify: `src/fulfillment/api.py:222-243` (create_stock_alert route — the `@app.post("/api/alerts/stock")` handler)
- Test: `tests/test_api.py`

- [ ] **Step 1: Write failing test for updated stock alert endpoint**

In `tests/test_api.py`, add after `test_create_stock_alert` (line 96):

```python
def test_create_stock_alert_with_restock_qty(seeded_client):
    resp = seeded_client.post("/api/alerts/stock", json={
        "picker_id": 1,
        "product_name": "Isopropyl Alcohol 1 Gal",
        "product_sku": "IPA-1GAL",
        "restock_qty": 10,
        "order_id": 1,
        "order_number": "1001",
    })
    assert resp.status_code == 200
    alerts = seeded_client.get("/api/alerts/stock/today").json()
    assert len(alerts) == 1
    assert alerts[0]["restock_qty"] == 10
    assert alerts[0]["order_id"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/cruz/alliance-fulfillment && python -m pytest tests/test_api.py::test_create_stock_alert_with_restock_qty -v`
Expected: FAIL — endpoint doesn't pass `restock_qty`/`order_id` to DB

- [ ] **Step 3: Update the stock alert endpoint in api.py**

In `src/fulfillment/api.py`, replace the `create_stock_alert` route handler (lines 222-243):

```python
    @app.post("/api/alerts/stock")
    async def create_stock_alert(request: Request):
        if not check_picker_auth(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        body = await request.json()
        picker_id = body["picker_id"]
        product_name = body["product_name"]
        product_sku = body.get("product_sku", "")
        restock_qty = body.get("restock_qty", 0)
        order_id = body.get("order_id")
        order_number = body.get("order_number", "")
        alert_id = db.create_stock_alert(picker_id, product_name, product_sku, restock_qty=restock_qty, order_id=order_id)

        # Send SMS
        sms_number = db.get_setting("sms_number", "")
        if sms_number:
            picker = db.get_picker(picker_id)
            picker_name = picker["name"] if picker else "Unknown"
            now_str = datetime.now(timezone.utc).strftime("%I:%M %p")
            message = sms.format_restock_message(product_name, restock_qty, order_number, picker_name, now_str)
            sent = sms.send_sms(sms_number, message)
            if sent:
                db.mark_alert_sent(alert_id)

        return {"alert_id": alert_id}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/cruz/alliance-fulfillment && python -m pytest tests/test_api.py::test_create_stock_alert_with_restock_qty -v`
Expected: PASS

- [ ] **Step 5: Run all API tests to check for regressions**

Run: `cd /home/cruz/alliance-fulfillment && python -m pytest tests/test_api.py -v`
Expected: All PASS (existing `test_create_stock_alert` still works — `restock_qty` and `order_id` default to 0/None)

- [ ] **Step 6: Commit**

```bash
cd /home/cruz/alliance-fulfillment
git add src/fulfillment/api.py tests/test_api.py
git commit -m "feat: update stock alert endpoint with restock_qty and order_id"
```

---

## Chunk 2: Frontend Changes

### Task 4: Update picker UI — per-item restock inputs + Print All button

**Files:**
- Modify: `src/fulfillment/templates/picker.html`

This task modifies the picker template with three changes:
1. Remove the global "Flag Low Stock" section (lines 79-84)
2. Remove per-order "Print Slip" button and add per-item restock qty inputs in `renderBatch()`
3. Add "Print All Slips" button at the top of the batch
4. Add `flagRestock()` JS function and update `printSlip()` to `printAllSlips()`

- [ ] **Step 1: Remove the global "Flag Low Stock" HTML section**

In `src/fulfillment/templates/picker.html`, delete lines 79-84 (the `<div class="stock-alert">` block):

```html
            <!-- Low Stock Alert -->
            <div class="stock-alert">
                <strong>Flag Low Stock:</strong><br>
                <input type="text" id="stock-product" placeholder="Product name...">
                <button onclick="flagLowStock()">Send</button>
            </div>
```

- [ ] **Step 2: Add CSS for restock inputs**

In `src/fulfillment/templates/picker.html`, add these styles after the existing `.status-msg.error` rule (after line 44):

```css
        .restock-row { display: flex; align-items: center; gap: 0.25rem; margin-top: 0.25rem; }
        .restock-row input { width: 60px; padding: 0.25rem; border: 1px solid #ddd; border-radius: 4px; font-size: 0.8rem; text-align: center; }
        .restock-row button { padding: 0.25rem 0.5rem; background: #e67e22; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 0.75rem; }
        .restock-row .restock-sent { color: #27ae60; font-size: 0.8rem; font-weight: bold; }
        .print-all-btn { width: 100%; padding: 0.75rem; font-size: 1rem; background: #3498db; color: white; border: none; border-radius: 8px; cursor: pointer; margin-bottom: 0.5rem; }
```

- [ ] **Step 3: Update renderBatch() to show per-item restock inputs and Print All button**

Replace the `renderBatch()` function in `<script>` (lines 139-169) with:

```javascript
        let currentBatchOrderIds = [];

        function renderBatch(orders) {
            const container = document.getElementById('batch-container');
            if (orders.length === 0) {
                container.innerHTML = '<div class="status-msg">No orders in queue right now. Check back soon.</div>';
                currentBatchOrderIds = [];
                return;
            }
            currentBatchOrderIds = orders.map(o => o.id);
            let html = `<div class="batch-header"><strong>Your Batch (${orders.length} orders)</strong></div>`;
            html += `<button class="print-all-btn" onclick="printAllSlips()">Print All Slips</button>`;
            let lastZone = '';
            for (const order of orders) {
                if (order.zone !== lastZone && lastZone !== '') {
                    html += `<div class="zone-divider">Zone: ${lastZone} \u2192 ${order.zone}</div>`;
                }
                lastZone = order.zone;
                let itemsHtml = '';
                for (let idx = 0; idx < order.line_items.length; idx++) {
                    const li = order.line_items[idx];
                    const sku = li.sku || '';
                    const name = li.name || '';
                    const escapedName = name.replace(/'/g, "\\'").replace(/"/g, '&quot;');
                    const escapedSku = sku.replace(/'/g, "\\'").replace(/"/g, '&quot;');
                    itemsHtml += `
                        <div class="restock-row" id="restock-${order.id}-${idx}">
                            <span>${li.quantity}x ${name}</span>
                            <input type="number" min="1" placeholder="Restock qty" id="qty-${order.id}-${idx}">
                            <button onclick="flagRestock(${order.id}, '${order.order_number}', '${escapedName}', '${escapedSku}', ${idx})">Restock</button>
                        </div>`;
                }
                html += `
                    <div class="order-card ${order.age_bracket}" id="order-${order.id}">
                        <div class="order-header">
                            <span>#${order.order_number}</span>
                            <span class="order-age">${Math.round(order.age_hours)}h old</span>
                        </div>
                        <div class="order-items">${itemsHtml}</div>
                        <div class="order-customer">${order.customer_name} \u2014 ${order.ship_to_state}</div>
                        <div class="actions">
                            <button class="btn-complete" onclick="completeOrder(${order.id})">Complete</button>
                            <button class="btn-problem" onclick="problemOrder(${order.id})">Problem</button>
                        </div>
                    </div>`;
            }
            container.innerHTML = html;
        }
```

- [ ] **Step 4: Replace printSlip() and flagLowStock() with printAllSlips() and flagRestock()**

Remove the `printSlip()` function (lines 171-173) and the `flagLowStock()` function (lines 199-211). Replace with:

```javascript
        function printAllSlips() {
            for (const orderId of currentBatchOrderIds) {
                window.open(`/api/orders/${orderId}/packing-slip`, '_blank');
            }
        }

        async function flagRestock(orderId, orderNumber, productName, productSku, idx) {
            const input = document.getElementById(`qty-${orderId}-${idx}`);
            const qty = parseInt(input.value);
            if (!qty || qty < 1 || !pickerId) return;
            await fetch('/api/alerts/stock', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    picker_id: pickerId,
                    product_name: productName,
                    product_sku: productSku,
                    restock_qty: qty,
                    order_id: orderId,
                    order_number: orderNumber,
                })
            });
            const row = document.getElementById(`restock-${orderId}-${idx}`);
            row.querySelector('input').style.display = 'none';
            row.querySelector('button').outerHTML = '<span class="restock-sent">\u2713 Sent</span>';
        }
```

- [ ] **Step 5: Verify the picker page loads without JS errors**

Run the app and open `http://localhost:8000/picker` in a browser. Verify:
- No JavaScript console errors
- Picker sign-in works
- Get batch shows orders with per-item restock inputs
- "Print All Slips" button appears above orders
- No "Print Slip" buttons on individual orders
- No "Flag Low Stock" section at the bottom

- [ ] **Step 6: Commit**

```bash
cd /home/cruz/alliance-fulfillment
git add src/fulfillment/templates/picker.html
git commit -m "feat: per-item restock inputs and Print All Slips button in picker UI"
```

---

### Task 5: Update manager dashboard to show restock quantity

**Files:**
- Modify: `src/fulfillment/templates/manager.html:224-238` (refreshAlerts function)

- [ ] **Step 1: Update the alerts display to include restock quantity**

In `src/fulfillment/templates/manager.html`, update the `refreshAlerts()` function (lines 224-238). Replace the alert rendering template:

```javascript
        async function refreshAlerts() {
            const resp = await fetch('/api/alerts/stock/today');
            const alerts = await resp.json();
            if (alerts.length === 0) {
                document.getElementById('alerts-area').innerHTML = '<span style="color:#999">No alerts today</span>';
                return;
            }
            document.getElementById('alerts-area').innerHTML = alerts.map(a => `
                <div class="alert-item">
                    <span class="alert-time">${a.flagged_at}</span> \u2014
                    <strong>${a.picker_name}</strong> \u2014
                    ${a.restock_qty ? a.restock_qty + 'x ' : ''}${a.product_name}
                    ${a.sms_sent ? '(SMS sent)' : ''}
                </div>
            `).join('');
        }
```

- [ ] **Step 2: Verify the manager page shows restock quantities**

Open `http://localhost:8000/manager` and verify the Low Stock Alerts section shows quantity when available (e.g., "10x Acetone - 1 Gallon").

- [ ] **Step 3: Commit**

```bash
cd /home/cruz/alliance-fulfillment
git add src/fulfillment/templates/manager.html
git commit -m "feat: show restock quantity in manager dashboard alerts"
```

---

### Task 6: Run full test suite

- [ ] **Step 1: Run all tests**

Run: `cd /home/cruz/alliance-fulfillment && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Fix any failures**

If any tests fail, diagnose and fix before proceeding.

- [ ] **Step 3: Final commit if any fixes were needed**

```bash
cd /home/cruz/alliance-fulfillment
git add -A
git commit -m "fix: resolve test failures from restock/print-all changes"
```
