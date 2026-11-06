# Example: `ci-failure-analyzer`

**Setup:** a demo branch with two commits that each break something:

1. A "developer" commit, *Simplify stock calculation in on_hand*, that removes the rule
   "blocked NiO pallets don't count as stock" (a **product bug**).
2. A "QA" commit, *Align product test with new response wording*, that changes a smoke test to expect
   `CREATED` instead of `ACCEPTED` (a **test bug**).

A real GitHub Actions run went red. The agent got only the run number.

**What makes this triage useful**

- CI reported **1** failure. The agent noticed that the smoke gate had skipped full regression, ran the full
  suite itself and found **3 failures from 2 causes**. It also ran `main` as a baseline.
- It separated the **test bug** (QA fixes it) from the **product bug** (Dev fixes it) and pointed to the exact commit for each.
- It saw that the test bug was **hiding** the product bug: fixing only the visible failure would have revealed two more.
- It blocked the release for a business reason: failed-check goods could be allocated and shipped.
- It found a **weakness in the pipeline itself**: when the smoke gate fails, no report is written and the summary
  step crashes. That was fixed in commit `8a0e6c6`.

---

## Agent output

### Triage: run 42291402193, branch demo/ci-red

**Verdict:** CI reported 1 failure. The full suite actually has 3 failures from 2 causes. 2 of them come from a
product bug in the stock calculation (commit 2f43271): blocked NiO pallets are now counted as stock. The CI run
never caught it. The third is a test bug (commit 19c687d).

**The CI run did not give the full picture.** The `Smoke tests` gate failed, so `Full regression` was skipped.
Only the smoke subset ran: 10 tests, 1 failed, 37 deselected. Because of that, `reports/junit.xml` and
`report.html` were never written:
- The `Write summary to the run page` step crashed with `FileNotFoundError: reports/junit.xml`.
- The `test-report` artifact was empty ("No files were found with the provided path: reports/").

To fill the gap I ran the full suite locally on the tested commit 19c687d: 3 failed, 44 passed. As a baseline I
ran a snapshot of main (6b3c411): 47 passed. I re-ran the 3 failing tests 3 times and they failed the same way
every time. None of them is flaky or an environment problem.

**Tested commit:** 19c687d. What changed since main (6b3c411), 2 commits:
- `2f43271` Simplify stock calculation in on_hand (`wms_app/main.py`, author "Demo Dev")
- `19c687d` Align product test with new response wording (`tests/api/test_products.py`, author "Demo QA")

| Test | Class | Root cause (one line) | Evidence | Next action | Owner |
|---|---|---|---|---|---|
| `tests/api/test_receiving.py::test_nio_pallet_is_blocked_and_adds_no_stock` (not run in CI) | Product bug | `on_hand()` dropped the `tu["status"] == "AVAILABLE"` filter, so BLOCKED NiO pallets count as stock. CLAUDE.md says onHand counts available TUs only. | `assert 60.0 == 0` on onHand after a NOK infeed. Fails 3/3 locally; passes on main. | Revert the on_hand change in 2f43271 (put the AVAILABLE filter back) | Dev |
| `tests/api/test_orders.py::test_nio_pallet_stock_cannot_be_allocated` (not run in CI) | Product bug, same cause as above | Release allocates stock on a BLOCKED NiO pallet | `release_order` returns 200, expected 409. Fails 3/3; passes on main. | Fixed by the same revert. Re-run the full regression afterwards. | Dev |
| `tests/api/test_products.py::test_create_product` (smoke, failed in CI) | Test bug | 19c687d changed the expected status to `CREATED`. The app still returns `ACCEPTED` for product create, as it does for every interface endpoint. The app code for this response did not change. | CI log and local: `{'status': 'ACCEPTED'} != {'status': 'CREATED'}`. Fails 3/3; passes on main. | Revert the assertion in 19c687d to `ACCEPTED` | QA |

The real bug sits in `wms_app/main.py` at `on_hand()`:
```python
def on_hand(product_id: str) -> float:
    """Physical stock on all pallets in the warehouse."""
    return sum(lu["quantity"]
               for tu in transport_units.values()
               for lu in tu["loadUnits"] if lu["productId"] == product_id)
```
On main, this generator also had `if tu["status"] == "AVAILABLE"`.

**CI pipeline issue (DevOps / QA, not a release blocker):** `.github/workflows/tests.yml` writes
`--junitxml`/`--html` only in the Full regression step. So whenever smoke fails, the summary step crashes and the
report artifact is empty. Two possible fixes: have the smoke step write its own junit file, or make the summary step
skip when the file is missing.

**Release decision: Block.** Stock is a P1 flow. Blocked (NiO) pallets now count as on-hand stock and can be
allocated and picked during order release. That means goods that failed the infeed check could be shipped. This
bug only showed up because I ran the full suite locally. The smoke gate hid it behind the test bug.

**Also worth noting:** the test bug masked the product bug. If someone "fixes" only the smoke test, the next run
would show these 2 product-bug failures in full regression.

**Offer:** I can hand the on_hand product bug (one bug report covering both failures) to the `bug-report-writer` agent.
