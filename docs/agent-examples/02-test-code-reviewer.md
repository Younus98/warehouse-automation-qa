# Example: `test-code-reviewer`

**Setup:** a branch added four new tests that were deliberately written with common mistakes
(status-code-only checks, a full JSON body and a raw `http.post`, `time.sleep`, CSS/text locators,
no side-effect checks, no markers). **All four tests passed**, which is exactly why they are dangerous:
a green test that cannot fail gives false confidence.

The agent was asked to review the branch against `main`.

**What makes this review useful:** it did not just read the code. It **broke the app three times on purpose**
and showed that none of the new tests noticed, while the existing tests did. Then it restored the app.

---

## Agent output

**Verdict: Needs rework**

Reviewed the commit adding:
- `tests/api/test_infeed_extra.py`
- `tests/ui/test_receiving_extra.py`

**Test run:** `pytest tests/api/test_infeed_extra.py tests/ui/test_receiving_extra.py -q` gave 4 passed.
The UI test took 2.18 s, and 2 s of that is `time.sleep(2)`.

**Break tests:** I broke `wms_app/main.py` three times and ran the new tests next to the existing ones in
`tests/api/test_receiving.py`. After each break I restored the file with `git checkout wms_app/main.py`,
and `git diff` shows it is clean.

| Break in the app | New test | Existing test |
|---|---|---|
| `WEIGHT_TOLERANCE` changed from 0.05 to 0.50 (weight check turned off) | `test_overweight_pallet` **still passed** | `test_weight_tolerance_boundaries` failed 2 cases |
| ASN not saved (`asns[tu.tuId] = ...` removed) | `test_asn` **still passed** | `test_asn_is_accepted_and_announced` failed |
| A NIO pallet set to `AVAILABLE` and RECEIPT stock booked | `test_wrong_type_rejected` **still passed** | `test_nio_pallet_is_blocked_and_adds_no_stock` failed |

None of the three new API tests caught the break aimed at it. The existing tests caught all three.

---

**[Blocker] tests/api/test_infeed_extra.py:13-16 - `test_overweight_pallet` cannot fail**
Why it matters: the infeed endpoint returns 201 for both OK and NIO, and 470 kg against 420 kg is an 11.9 %
deviation (should be NIO), so checking only the status code proves nothing. It passed with the weight check turned off.
Fix:
```python
@pytest.mark.negative
def test_overweight_pallet_goes_to_nio_and_adds_no_stock(wms, product):
    wms.create_asn(builders.asn("PAL-0001", weight=420.0))

    result = wms.infeed_scan("PAL-0001", "EURO", 470.0).json()

    assert result["result"] == "NIO"
    assert "deviates 11.9%" in result["reasons"][0]
    tu = wms.get_transport_unit("PAL-0001").json()
    assert (tu["location"], tu["status"]) == ("NIO-01", "BLOCKED")
    assert wms.get_stock(product).json()["onHand"] == 0
    assert wms.get_transactions(product).json() == []
```
This largely repeats `test_weight_tolerance_boundaries` and `test_nio_pallet_is_blocked_and_adds_no_stock`.
Consider deleting it instead.

**[Blocker] tests/ui/test_receiving_extra.py:12-13 - fixed `time.sleep(2)` and a plain `assert` on UI text**
Why it matters: the test will fail on a slow CI runner and wastes 2 s on every run. `inner_text` reads the text
once, with no retry.
Fix: use `expect(wms_page.message).to_have_text("Pallet PAL-0001 OK - stored at STORAGE-01")`.
An exact match also stops a substring like "OK" from matching unrelated text.

**[Blocker] tests/ui/test_receiving_extra.py:8-11 - text, name and CSS-class locators instead of the page object**
Why it matters: `text=Receiving`, `input[name=...]` and `.action` break on a label or style change. `.action` is
also on the Release and Complete buttons, so the click only works because the infeed button comes first in the page.
The TU type is never chosen, so the test depends on the dropdown's default value.
Fix: `wms_page.scan_pallet("PAL-0001", "EURO", 420.0)`. The page object already handles this with `data-testid`.

**[Major] tests/ui/test_receiving_extra.py:5 - duplicates an existing UI test (wrong layer, no added value)**
Why it matters: `test_scanning_matching_pallet_shows_ok_and_updates_stock` in `tests/ui/test_wms_screens.py`
already covers this flow, and it also checks stock and location. This test is the same flow with weaker checks.
Fix: delete the file. If something is meant to be new here, say what and assert it with `expect`.

**[Major] tests/api/test_infeed_extra.py:5-10 - `test_asn` builds the full JSON by hand, calls `http.post` directly, and checks only the status code**
Why it matters: it breaks rules 3 and 4, and it passed even when the ASN was never saved.
`test_asn_is_accepted_and_announced` already covers this properly.
Fix: delete it. If you keep it, it should be:
```python
@pytest.mark.smoke
def test_asn_is_accepted_and_announced(wms, product):
    response = wms.create_asn(builders.asn("PAL-0009"))

    assert response.status_code == 201
    assert wms.get_asn("PAL-0009").json()["status"] == "ANNOUNCED"
```

**[Major] tests/api/test_infeed_extra.py:19-22 - `test_wrong_type_rejected` has no side-effect checks**
Why it matters: rule 6 says a rejection must be checked for side effects. The test passed while a NIO pallet was
made AVAILABLE and stock was booked.
Fix: after the `result` check, add the TU location/status (`NIO-01`/`BLOCKED`), `onHand == 0`, the
empty-transactions checks from the overweight fix above, and the reason text `"TU type TOTE does not match ASN EURO"`.
Or turn the existing `test_wrong_tu_type_goes_to_nio` into a parametrize over `INDU`/`TOTE` with ids.

**[Major] both files - missing markers**
Why it matters: rule 8. The two rejection tests have no `negative` marker, so `pytest -m negative` skips them.
Fix: add `@pytest.mark.negative` to the overweight and wrong-type tests.

**[Minor] names do not describe the behaviour, and Arrange-Act-Assert is not separated**
Why it matters: rules 1 and 2. A failure named `test_asn` or `test_scan_from_ui` does not tell the reader what broke.
Fix: use names like `test_overweight_pallet_goes_to_nio_and_adds_no_stock` and
`test_wrong_tu_type_pallet_is_blocked_without_stock`, with blank lines between the three blocks.

**Coverage note:** the API tests already cover every branch the new tests touch (type mismatch, both weight edges,
NIO side effects, no ASN, scanning twice). After the fixes, the only real addition is a TOTE type-mismatch variant.

**What is good:** the new API tests use the `wms`/`product` fixtures for a clean warehouse, and two of them already
use `builders.asn(...)` and `wms.infeed_scan(...)`, so the fixes are small.
