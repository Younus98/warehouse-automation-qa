# Example: `test-case-designer`

**Input given to the agent**

> For safety, the storage racks are rated for at most 1,000 kg per pallet. At the infeed, any EURO or INDU
> pallet whose scale weight is above 1,000 kg must be sent to NiO with the reason 'Max pallet weight exceeded',
> even when it matches its ASN weight. The host must also not be able to announce a pallet above 1,000 kg:
> the ASN must be rejected. Totes are not affected (they have their own limit, to be defined later).

The feature was **not implemented**. The agent read the current ASN and infeed code to see where the rule would sit
and how it interacts with the existing ±5 % weight check and TU type check.

**What it found that a quick read of the requirement misses**

- **The 1,000.1-1,050 kg gap:** with the ASN capped at 1,000 kg, the ±5 % tolerance would still let a 1,050 kg
  pallet through as OK. The infeed rule is the only thing protecting that band, so it is tested first.
- **A real gap in the existing system (Q6):** transport orders do not check TU status, so a BLOCKED pallet can be
  moved from NIO-01 straight into storage, which goes around the safety rule.

---

## Agent output

### Test design: max pallet weight 1,000 kg (ASN and infeed)

**Scope:** a new 1,000 kg limit for EURO and INDU pallets, checked at ASN create (`/interface/asns/asn-create`) and at
the infeed check (`/api/receiving/infeed`), plus the existing ±5 % and TU type checks it interacts with. TOTE is excluded.

**Assumptions** (each one is also an open question below):
- 1,000.0 kg is allowed and the limit is strictly "> 1000".
- Scale resolution is 0.1 kg, the same step the existing tolerance tests use.
- An ASN rejection returns 422, like the other ASN validations.
- At the infeed the rule uses the **scanned** TU type, because that is the physical carrier going into the rack.
- The reason text is exactly `Max pallet weight exceeded`.

**Where the rule would sit in `wms_app/main.py`:**
- `asn_create`: a new check after the `tuType` check. The ordering against the duplicate-TU check (409) and the
  unknown-product check (422) is not defined yet.
- `infeed_scan`: one more entry added to `reasons`. The code already collects every failing reason, so one scan can
  come back with type mismatch, deviation and max weight together. The NIO branch then gives `NIO-01`, `BLOCKED`,
  ASN `NIO` and no RECEIPT.

**Main interaction:** once the ASN is capped at 1,000 kg, the ±5 % tolerance still lets a scale reading up to
1,050 kg through as OK. The 1,000.1-1,050.0 kg band is the only place where the new infeed rule changes the result
on its own. That band is the most important thing to test.

**Existing coverage in `tests/api/test_receiving.py`:** nothing covers max weight. The only weight tests use a 420 kg
pallet: `test_weight_tolerance_boundaries`, `test_nio_pallet_is_blocked_and_adds_no_stock` and
`test_wrong_tu_type_goes_to_nio`. These are regression anchors that must still pass. The new cases reuse their
patterns and the `builders.asn(tu_type=..., weight=...)` and `product` fixtures. No new builder is needed.

| ID | Title | Preconditions | Steps | Expected result | Technique | Priority | Automate? |
|---|---|---|---|---|---|---|---|
| TC-ASN-01 | ASN for pallet at exactly 1,000 kg is accepted | Product SKU-100 exists | Create ASN PAL-0001, EURO and INDU (parametrized), weight 1000.0 | 201 ACCEPTED; GET ASN shows ANNOUNCED with weight 1000.0 | Boundary value analysis (on) | P1 | API |
| TC-ASN-02 | ASN for pallet just under the limit is accepted | SKU-100 exists | Create ASN EURO/INDU, weight 999.9 | 201; ANNOUNCED | BVA (just inside) | P2 | API |
| TC-ASN-03 | ASN for pallet just over the limit is rejected | SKU-100 exists | Create ASN EURO/INDU, weight 1000.1 | 422 (to confirm); detail says max pallet weight exceeded; GET /api/asns/PAL-0001 returns 404 | BVA (just outside) | P1 | API |
| TC-ASN-04 | ASN far above the limit is rejected | SKU-100 exists | Create ASN EURO, weight 1500 | 422; no ASN stored | Equivalence partitioning (invalid class) | P2 | API |
| TC-ASN-05 | Tote ASN above 1,000 kg is not affected | SKU-100 exists | Create ASN TOTE, weight 1000.1 and 1500 | 201; ANNOUNCED | Equivalence partitioning / decision table (TU type) | P2 | API |
| TC-ASN-06 | Rejected ASN leaves nothing behind | SKU-100 exists | Create ASN PAL-0001 EURO 1200 (rejected); list TUs, stock, transactions | No ASN, no TU, onHand 0, no transactions | Error guessing (side effects) | P1 | API |
| TC-ASN-07 | TU id can be announced again after an overweight rejection | TC-ASN-06 done | Create ASN PAL-0001 EURO 900 | 201 (not 409 "already announced") | State transition | P2 | API |
| TC-ASN-08 | Host resends the same overweight ASN | SKU-100 exists | Send ASN EURO 1200 twice | Both 422 with the max-weight reason; the second is not 409 | Error guessing (duplicate host message) | P3 | API |
| TC-ASN-09 | Overweight plus unknown product: which error wins | No product SKU-X | ASN EURO 1200, product SKU-X | One defined status and message (see Q3); nothing stored | Decision table | P3 | API |
| TC-ASN-10 | Overweight ASN for a TU id already in stock | `stocked_pallet` (PAL-0001) | ASN PAL-0001 EURO 1200 | One defined code, 409 or 422 (see Q3); existing TU and stock unchanged | Decision table | P3 | API |
| TC-ASN-11 | Regression: other ASN validations still work | SKU-100 exists | Unknown tuType, weight 0, qty 0, no lines | 422 for each | Regression | P2 | API (covered: `test_invalid_asn_is_rejected`) |
| TC-INF-01 | Pallet at exactly 1,000 kg matching its ASN goes to storage | ASN PAL-0001 EURO/INDU 1000.0 | Infeed scan with same type, 1000.0 | OK, STORAGE-01, AVAILABLE; ASN RECEIVED; one RECEIPT +60; onHand 60 | BVA (on) | P1 | API |
| TC-INF-02 | Pallet just over 1,000 kg goes to NiO although it is within ±5 % | ASN EURO/INDU 1000.0 | Scan same type, 1000.1 | NIO, reasons == ["Max pallet weight exceeded"] only (deviation 0.01 % is fine) | BVA (just outside) + decision table | P1 | API |
| TC-INF-03 | Pallet at +5.0 % of a 1,000 kg ASN | ASN EURO 1000.0 | Scan EURO 1050.0 | NIO, reasons == max weight only (deviation exactly 5.0 % is still OK) | BVA (tolerance edge meets max edge) | P1 | API |
| TC-INF-04 | Pallet over both limits gets both reasons | ASN EURO 1000.0 | Scan EURO 1050.1 | NIO; reasons contain the deviation reason **and** the max-weight reason | Decision table | P2 | API |
| TC-INF-05 | Light ASN, scale just over 1,000 kg within tolerance | ASN EURO 960.0 | Scan EURO 1000.0, then (separate test) 1000.1 | 1000.0 gives OK; 1000.1 gives NIO with max weight only | BVA | P2 | API |
| TC-INF-06 | NiO for max weight: blocked TU, no stock | ASN EURO 1000.0 | Scan EURO 1020; check TU, ASN, stock, transactions | TU NIO-01 / BLOCKED; ASN status NIO; onHand 0, available 0; no RECEIPT | Side effects | P1 | API |
| TC-INF-07 | Overweight tote is not affected | ASN TOTE 1200 | Scan TOTE 1200 | OK, STORAGE-01; stock booked; no max-weight reason | Equivalence partitioning | P2 | API |
| TC-INF-08 | Scanned type decides: ASN TOTE, physically a EURO pallet, 1,100 kg | ASN TOTE 1100 | Scan EURO 1100 | NIO; reasons contain the type mismatch **and** max weight (if Q4 = scanned type) | Decision table | P2 | API |
| TC-INF-09 | Scanned type decides: ASN EURO, physically a TOTE | ASN EURO 1000 | Scan TOTE 1020 | NIO; type mismatch only, no max-weight reason (if Q4 = scanned type) | Decision table | P3 | API |
| TC-INF-10 | Type mismatch between pallets at 1,020 kg | ASN EURO 1000 | Scan INDU 1020 | NIO; both type-mismatch and max-weight reasons | Decision table | P3 | API |
| TC-INF-11 | ASN announced before the release, above 1,000 kg | ASN EURO 1200 in ANNOUNCED, created before deploy | Scan EURO 1200 | NIO, max weight (the infeed rule is the safety net for old data) | Error guessing (migration) | P2 | Manual (needs pre-release data) |
| TC-INF-12 | Overweight NiO pallet cannot be scanned again | TC-INF-06 done | Scan PAL-0001 EURO 1000 | 409 "already NIO"; TU stays BLOCKED in NIO-01, no RECEIPT | State transition | P2 | API (pattern of `test_same_pallet_cannot_be_received_twice`) |
| TC-INF-13 | Regression: 420 kg tolerance boundaries unchanged | ASN EURO 420 | 399.0 / 398.9 / 441.0 / 441.1 | OK / NIO / OK / NIO; no max-weight reason | Regression | P1 | API (covered: `test_weight_tolerance_boundaries`) |
| TC-INF-14 | Regression: normal NiO side effects | ASN 420, scan 500 | Check TU and stock | NIO-01 / BLOCKED, no stock | Regression | P2 | API (covered: `test_nio_pallet_is_blocked_and_adds_no_stock`) |
| TC-ORD-01 | Order cannot use stock on an overweight NiO pallet | TC-INF-06 (only pallet is in NiO); ORD-1 for 24 x SKU-100, short allocation false | Release ORD-1 | 409 (no or insufficient stock); order NEW; no PICK tasks; allocated 0 | Warehouse edge case (blocked stock) | P2 | API |
| TC-ORD-02 | Short allocation ignores the NiO pallet and uses only the good pallet | PAL-0001 OK (1000 kg, 60 pcs); PAL-0002 NiO (1020 kg, 60 pcs); ORD-1 for 100, short allocation true | Release ORD-1 | RELEASED; PICK task only on PAL-0001, qty 60; quantityAllocated 60; allocated 60 | Warehouse edge case (partial stock) | P3 | API |
| TC-TO-01 | Moving an overweight NiO pallet into storage | TC-INF-06 done | Transport order PAL-0001 from NIO-01 to STORAGE-01 | Expected behaviour not defined: today the code accepts it (no TU status check), which goes around the safety rule (see Q6) | Error guessing | P2 | API |
| TC-TASK-01 | No task is created by an overweight infeed | ASN EURO 1000 | Scan EURO 1020; GET /api/tasks | Empty task list | Side effects | P3 | API |
| TC-INF-15 | UI shows the max-weight reason | ASN EURO 1000 (via API) | Open Receiving, scan PAL-0001 EURO 1020 | Message "Pallet PAL-0001 NIO: Max pallet weight exceeded"; Inventory row status BLOCKED | Equivalence partitioning | P2 | UI |
| TC-INF-16 | UI shows both reasons joined | ASN EURO 1000 | Scan EURO 1100 | Message has both the deviation and max-weight reasons, separated by "; " | Decision table | P3 | UI |

### Open questions
1. **Is the limit inclusive?** "At most 1,000 kg" reads as 1,000.0 allowed and 1,000.1 refused. Please confirm, and confirm the scale resolution (0.1 kg?), because that sets the "just outside" value.
2. **ASN rejection code and text.** Is it 422 like the other ASN validations? Does the detail use the same text "Max pallet weight exceeded"?
3. **Order of ASN checks.** If an ASN is overweight and also has an unknown product, or reuses a TU id that already exists, which error comes back (422 or 409)? The current code checks type, then duplicate, then product.
4. **Which TU type decides at the infeed: scanned or announced?** This matters on a type mismatch, e.g. ASN TOTE but a EURO pallet physically arrives. For rack safety the scanned type makes more sense.
5. **Reason text.** Exactly "Max pallet weight exceeded", or should it include the measured weight like the deviation reason does? Listed next to the other reasons (the current code reports them all) or replacing them?
6. **Moving NiO pallets.** `transport_order_create` does not check TU status, so an overweight BLOCKED pallet can be moved from NIO-01 to STORAGE-01. Is that intended (manual clarification), or should it be refused for overweight TUs?
7. **ASNs already announced above 1,000 kg before go-live.** Leave them for the infeed rule to catch, or cancel or flag them?
8. **The tote limit "to be defined later".** Should TOTE stay unlimited for now, or is there a provisional value that changes TC-ASN-05 and TC-INF-07?

### Automate first
1. **TC-INF-02 / TC-INF-03** (parametrized 1000.0 / 1000.1 / 1050.0 / 1050.1 with expected reasons). The ±5 % tolerance lets 1,000.1-1,050 kg pass as OK today, so this band is where an overweight pallet really reaches the rack.
2. **TC-ASN-01 / TC-ASN-03** (parametrized 1000.0 / 1000.1 x EURO/INDU, plus TOTE 1000.1 accepted). This checks the host-interface block and the tote exclusion in a few fast cases.
3. **TC-INF-06**. It shows the rule really prevents storage: the TU is blocked in NIO-01, there is no RECEIPT and onHand stays 0, not only that a NIO result comes back.
