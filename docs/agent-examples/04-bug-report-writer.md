# Example: `bug-report-writer`

**Input given to the agent:** the product bug from the CI triage (see `03-ci-failure-analyzer.md`):
two failing tests and the suspected commit.

**What makes this report useful**

- It **confirmed** the cause instead of trusting the suspicion: it ran the same steps against the parent commit
  and showed that the correct responses come back there.
- It explained **why** the order ends up RELEASED with nothing allocated: the stock check and the allocation now
  use different rules.
- The **wider-impact check** found much worse effects than the two tests showed: the "no short allocation" rule is
  silently bypassed, an order becomes PICKED while 40 units were never allocated, and stock no longer matches the
  inventory transaction log.
- It kept the unrelated test failure **out** of this ticket.

---

## Agent output

**Title:** `[Stock / Order Planner] Blocked NiO pallets are counted in onHand/available - orders release with 0 allocated instead of being refused`

**Severity / Priority:** Critical / High. Rejected (NiO) pallets show up as sellable stock. Orders that should be
refused get status RELEASED with nothing or only part allocated, even when `shortAllocationAllowed = false`.
The result is an order that looks fulfilled but ships short, and stock figures that no longer match the inventory
transaction log.

**Environment:**
- Commit `19c687d` (branch `demo/ci-red`). The regression was introduced in `2f43271` "Simplify stock calculation in on_hand".
- Run locally with `pytest tests/api -vv` (in-process FastAPI TestClient).
- CI run [42291402193](https://github.com/Younus98/warehouse-automation-qa/actions/runs/42291402193) stopped at the
  "Smoke tests" step, so "Full regression" never ran. These two failures were found only in the local full run.

**Preconditions**
- Clean warehouse (`POST /api/test/reset`).
- Product `SKU-100` exists (`POST /interface/products/product-create` with `samples/product_create.json`).

**Steps to reproduce**
1. `POST /interface/asns/asn-create` with the body from `samples/asn_create.json`:
   ```json
   {"asnType":"Receipt","owner":"DEMO","transportUnit":{"tuId":"PAL-0001","tuType":"EURO","weight":420.0},"asnLine":[{"lineNumber":1,"productId":"SKU-100","quantityExpected":60}]}
   ```
   Response `201 {"status":"ACCEPTED","tuId":"PAL-0001"}`
2. `POST /api/receiving/infeed` with `{"tuId":"PAL-0001","tuType":"EURO","weight":500.0}` (19 % overweight).
   Response `201 {"result":"NIO","location":"NIO-01","reasons":["Weight 500.0 kg deviates 19.0% from ASN 420.0 kg"]}`
3. `GET /api/transport-units/PAL-0001`
   Response `200 {"tuId":"PAL-0001","tuType":"EURO","location":"NIO-01","status":"BLOCKED",...}`. This is correct.
4. `GET /api/stock/SKU-100`
5. `POST /interface/orders/batch-create` with the order from `samples/order_batch_create.json` but orderId `ORD-1`
   (24 x SKU-100, `shortAllocationAllowed:false`, `orderRelease:false`). Response `200 ACCEPTED "Order received"`.
6. `POST /api/orders/ORD-1/release`
7. `GET /api/tasks?reference=ORD-1`

**Expected result**
From CLAUDE.md, Warehouse domain:
- "NOK -> `NIO-01`, TU `BLOCKED`, **no stock**."
- "`onHand` (**available TUs only**)".
- The Order Planner checks stock for every line first. With `shortAllocationAllowed = false` it refuses the release.

So:
- Step 4 returns `{"onHand":0,"allocated":0,"available":0}`.
- Step 6 returns `409 {"detail":"Insufficient stock for SKU-100: 0 available, 24 ordered"}` and the order stays `NEW`.

Verified: these are exactly the responses from the parent commit `6b3c411`.

**Actual result**
- Step 4: `200 {"productId":"SKU-100","onHand":60.0,"allocated":0,"available":60.0}`
- Step 6: `200 {..."shortAllocationAllowed":false,"orderLine":[{...,"quantityOrdered":24.0,"quantityAllocated":0.0}],"status":"RELEASED"}`
- Step 7: `200 []`. The order is RELEASED with no PICK tasks.
- `GET /api/inventory-transactions?productId=SKU-100` returns `[]`. No RECEIPT was booked, but stock still shows 60,
  so stock and the audit trail disagree.

**Evidence**
- `tests/api/test_receiving.py::test_nio_pallet_is_blocked_and_adds_no_stock`
  ```
  >       assert wms.get_stock(product).json()["onHand"] == 0
  E       assert 60.0 == 0
  ```
- `tests/api/test_orders.py::test_nio_pallet_stock_cannot_be_allocated`
  ```
  >       assert wms.release_order("ORD-1").status_code == 409
  E       AssertionError: assert 200 == 409
  ```
- The CI run (link above) did not reach these tests. They fail in the local full run.

**Notes**
- **Code location (confirmed by diff and by re-running against the parent commit):** `wms_app/main.py`, function
  `on_hand()`. Commit `2f43271` removed the filter `if tu["status"] == "AVAILABLE"` and changed the docstring from
  "Physical stock on AVAILABLE pallets (blocked NiO pallets don't count)" to "Physical stock on all pallets in the warehouse".
- **Why the release returns 200 with 0 allocated:** `release_order()` step 1 (the stock check) uses `on_hand()`,
  so it now sees the blocked 60. Step 2 (allocation) still skips TUs where `status != "AVAILABLE"`. The check passes,
  the allocation finds nothing, and the order is still set to `RELEASED`.
- **Wider impact (all reproduced at `19c687d`):**
  1. **Release on order creation** (`batch-create` with `orderRelease:true`) answers `"Order received and released"`
     with no tasks. The same happens with a NiO caused by a TU type mismatch, so the cause is any BLOCKED TU, not just overweight.
  2. **Release via `batch-update`** answers `ACCEPTED "Order released"` instead of `REJECTED "Insufficient stock..."`.
  3. **Mixed stock** (PAL-0001 OK with 60 + PAL-0002 NiO with 60, order 100, `shortAllocationAllowed:false`):
     - Stock shows `onHand 120 / available 120` instead of 60.
     - The release returns 200 with `quantityAllocated 60` and one PICK task. It should be 409 `"60 available, 100 ordered"`.
       The no-short-allocation rule is silently bypassed.
     - After completing the pick, the order becomes `PICKED` with 40 never allocated.
     - Stock shows `onHand 60`, but the transaction log nets to 0 (RECEIPT +60, PICK -60).
  4. **Every product on a NiO pallet is affected.** A two-line NiO ASN shows both products in `GET /api/stock`.
     The Inventory screen uses the same function, so it is suspected to show the same wrong numbers (UI not checked).
  5. **Not affected:** RECEIPT transactions are still booked only for OK pallets, and PICK tasks are never created on
     BLOCKED TUs, because the allocation loop still filters. Only the stock figures and the release check are wrong.
- **Unrelated failure in the same run:** `tests/api/test_products.py::test_create_product` also fails. It comes from
  commit `19c687d` and is a separate issue that should not go in this ticket.
