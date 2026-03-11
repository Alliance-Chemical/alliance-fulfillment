# Auto-Complete on Ship

**Goal:** When a picker ships an order via ShipStation's Scan tab, automatically mark it complete in the queue so the picker doesn't have to tap Complete manually.

**Mechanism:** During each sync, `remove_shipped_orders()` already knows which orders left `awaiting_shipment`. Currently it only deletes `status='queued'` orders. Change it to also auto-complete `status='assigned'` orders — set status to completed, credit the assigned picker via the completions table.

**Edge case:** If the picker taps Complete after the sync already auto-completed, prevent a duplicate completions record by checking status before inserting.
