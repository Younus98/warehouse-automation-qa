"""Orders and the Order Planner - receive, release, allocate stock."""
import pytest

from framework import builders


@pytest.mark.smoke
def test_order_is_accepted_with_status_new(wms, product):
    response = wms.create_orders(builders.order_batch(builders.order("ORD-1")))

    assert response.json()["results"][0]["status"] == "ACCEPTED"
    assert wms.get_order("ORD-1").json()["status"] == "NEW"


def test_one_bad_order_does_not_block_the_batch(wms, product):
    batch = builders.order_batch(
        builders.order("ORD-GOOD"),
        builders.order("ORD-BAD", product_id="SKU-DOES-NOT-EXIST"),
    )

    results = {r["orderId"]: r["status"] for r in wms.create_orders(batch).json()["results"]}

    assert results == {"ORD-GOOD": "ACCEPTED", "ORD-BAD": "REJECTED"}


@pytest.mark.negative
def test_duplicate_order_is_rejected(wms, product):
    wms.create_orders(builders.order_batch(builders.order("ORD-1")))

    result = wms.create_orders(builders.order_batch(builders.order("ORD-1"))).json()["results"][0]

    assert (result["status"], result["message"]) == ("REJECTED", "Duplicate orderId")


@pytest.mark.smoke
def test_release_allocates_stock_and_creates_pick_task(wms, stocked_pallet, product):
    wms.create_orders(builders.order_batch(builders.order("ORD-1", qty=24)))

    result = wms.update_orders({"order": [{"orderId": "ORD-1", "orderRelease": True}]}).json()["results"][0]

    assert result["message"] == "Order released"
    assert wms.get_order("ORD-1").json()["status"] == "RELEASED"
    assert wms.get_stock(product).json() == {"productId": product, "onHand": 60, "allocated": 24, "available": 36}

    tasks = wms.get_tasks(reference="ORD-1").json()
    assert [(t["type"], t["quantity"], t["tuId"]) for t in tasks] == [("PICK", 24, stocked_pallet)]


def test_order_with_release_flag_is_released_immediately(wms, stocked_pallet):
    wms.create_orders(builders.order_batch(builders.order("ORD-1", release=True)))

    assert wms.get_order("ORD-1").json()["status"] == "RELEASED"


@pytest.mark.negative
def test_release_refused_when_stock_is_insufficient(wms, stocked_pallet, product):
    wms.create_orders(builders.order_batch(builders.order("ORD-1", qty=100)))

    result = wms.update_orders({"order": [{"orderId": "ORD-1", "orderRelease": True}]}).json()["results"][0]

    assert result["status"] == "REJECTED"
    assert result["message"] == "Insufficient stock for SKU-100: 60 available, 100 ordered"
    assert wms.get_order("ORD-1").json()["status"] == "NEW"
    assert wms.get_tasks(reference="ORD-1").json() == []


def test_short_allocation_allocates_what_is_available(wms, stocked_pallet):
    wms.create_orders(builders.order_batch(builders.order("ORD-1", qty=100, short_allocation=True)))

    release = wms.release_order("ORD-1")

    assert release.status_code == 200
    assert release.json()["orderLine"][0]["quantityAllocated"] == 60


def test_stock_reserved_by_one_order_is_not_given_to_another(wms, stocked_pallet):
    wms.create_orders(builders.order_batch(builders.order("ORD-1", qty=50), builders.order("ORD-2", qty=20)))
    wms.release_order("ORD-1")

    response = wms.release_order("ORD-2")  # only 10 left

    assert response.status_code == 409


@pytest.mark.negative
def test_order_cannot_be_released_twice(wms, stocked_pallet):
    wms.create_orders(builders.order_batch(builders.order("ORD-1")))
    wms.release_order("ORD-1")

    assert wms.release_order("ORD-1").status_code == 409


def test_nio_pallet_stock_cannot_be_allocated(wms, product):
    wms.create_asn(builders.asn("PAL-0001", weight=420.0))
    wms.infeed_scan("PAL-0001", "EURO", 500.0)  # goes to NiO
    wms.create_orders(builders.order_batch(builders.order("ORD-1")))

    assert wms.release_order("ORD-1").status_code == 409
