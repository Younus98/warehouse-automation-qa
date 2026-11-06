# warehouse-automation-qa

QA automation framework for a mini Warehouse Management System (WMS).
Claude Code reads this file at the start of every session; the agents in
`.claude/agents/` follow the rules below.

## What is in the repo

| Path | What it is |
|---|---|
| `wms_app/main.py` | The system under test: a mini WMS (FastAPI, in-memory data) |
| `wms_app/static/index.html` | The WMS screen (Inventory, Receiving, Orders, Tasks) |
| `framework/wms_client.py` | One method per endpoint - tests never build URLs themselves |
| `framework/builders.py` | Valid test messages; a test changes only the field it is about |
| `framework/pages/wms_page.py` | Page Object for the screen |
| `tests/conftest.py` | Fixtures: `wms` (clean warehouse), `product`, `stocked_pallet` |
| `tests/api/` | API tests (pytest) |
| `tests/ui/` | UI tests (Playwright) - setup through the API, verification in the browser |
| `samples/` | Example host-interface messages |
| `.github/workflows/tests.yml` | CI: smoke gate, then full regression with reports |

## Warehouse domain

- **Product** - master data, sent by the host (ERP) through `/interface/products/product-create`.
- **ASN (Advance Shipping Notice)** - announces one transport unit and its lines before it arrives.
- **Transport Unit (TU)** - physical carrier: `EURO` pallet, `INDU` pallet, `TOTE`.
- **Load Unit (LU)** - stock of one product on a TU.
- **Infeed ASN check** - on arrival the TU type must match the ASN and the weight must be within +/- 5 %.
  OK -> `STORAGE-01`, TU `AVAILABLE`, RECEIPT booked. NOK -> `NIO-01` (nicht in Ordnung), TU `BLOCKED`, no stock.
- **Stock** - `onHand` (available TUs only), `allocated` (open PICK tasks), `available` = onHand - allocated.
- **Order** - arrives in a batch; each order is accepted or rejected on its own. Status `NEW -> RELEASED -> PICKED`.
- **Order Planner / release** - checks stock for every line first, then creates one PICK task per pallet used.
  `shortAllocationAllowed` decides between refusing and allocating what is available.
- **Task** - `PICK` (reduces stock, books a PICK transaction) or `MOVE` (changes TU location).
- **Transport order** - moves a TU; refused if the TU is not at the source, source = destination, or the TU has an open task.
- **Inventory transaction** - audit trail: `RECEIPT` (+qty) and `PICK` (-qty), with a reference (ASN or order).

## Test rules (follow these in every test)

1. **Arrange - Act - Assert**, separated by a blank line. One behaviour per test.
2. Test names say the behaviour: `test_release_refused_when_stock_is_insufficient`.
3. Use `builders.*` for request bodies. Never write a full JSON body inside a test.
4. Use `wms.*` client methods. Never call `http.post("/...")` inside a test.
5. Use fixtures for setup (`product`, `stocked_pallet`, ...). Every test starts with a clean warehouse.
6. Check **side effects**, not just the response: after a rejection, assert that status, stock and tasks did not change.
7. Boundaries and variations use `@pytest.mark.parametrize` with `ids` when the values are not self-explanatory.
8. Markers: `smoke` for the few most important checks, `negative` for invalid input or rule violations.
9. UI tests: create data through the API, use the UI only for what is being tested.
   Locators use `data-testid` through the page object. Use Playwright `expect(...)`, never `time.sleep`.
10. Use neutral demo data only (`DEMO`, `SKU-100`, `PAL-0001`). No real customer, product or company names.

## Commands

```bash
pytest                  # everything
pytest -m smoke         # quick check
pytest tests/api -m negative
uvicorn wms_app.main:app --reload    # start the WMS, screen at http://localhost:8000, API docs at /docs
```

## QA agents

| Agent | Use it for |
|---|---|
| `test-case-designer` | Requirement or user story -> structured test cases |
| `test-code-reviewer` | Review new or changed tests against the rules above |
| `bug-report-writer` | Failed test -> ready-to-file bug report |
| `ci-failure-analyzer` | Failed CI run -> each failure classified as product bug, test bug, flaky or environment |
