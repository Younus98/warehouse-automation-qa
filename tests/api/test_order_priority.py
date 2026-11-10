"""Priority-based order release - higher priority (lower number) gets stock first."""
import pytest

from framework import builders


@pytest.mark.smoke
def test_priority_1_released_before_priority_5_when_stock_is_limited(wms, stocked_pallet, product):
    batch = builders.order_batch(
        builders.order("ORD-LO", qty=40, priority=5, release=True),
        builders.order("ORD-HI", qty=40, priority=1, release=True),
    )

    results = {r["orderId"]: r for r in wms.create_orders(batch).json()["results"]}

    assert results["ORD-HI"]["message"] == "Order received and released"
    assert "release failed" in results["ORD-LO"]["message"]
    assert wms.get_order("ORD-HI").json()["status"] == "RELEASED"
    assert wms.get_order("ORD-LO").json()["status"] == "NEW"
    assert wms.get_tasks(reference="ORD-LO").json() == []
    assert wms.get_stock(product).json() == {
        "productId": product, "onHand": 60, "allocated": 40, "available": 20,
    }


def test_both_orders_released_when_stock_is_sufficient_regardless_of_priority(wms, stocked_pallet, product):
    batch = builders.order_batch(
        builders.order("ORD-LO", qty=20, priority=5, release=True),
        builders.order("ORD-HI", qty=20, priority=1, release=True),
    )

    results = {r["orderId"]: r for r in wms.create_orders(batch).json()["results"]}

    assert results["ORD-LO"]["message"] == "Order received and released"
    assert results["ORD-HI"]["message"] == "Order received and released"
    assert wms.get_order("ORD-LO").json()["status"] == "RELEASED"
    assert wms.get_order("ORD-HI").json()["status"] == "RELEASED"
    assert wms.get_stock(product).json() == {
        "productId": product, "onHand": 60, "allocated": 40, "available": 20,
    }


@pytest.mark.negative
def test_rejected_low_priority_order_has_no_tasks_and_stock_unchanged(wms, stocked_pallet, product):
    batch = builders.order_batch(
        builders.order("ORD-LO", qty=50, priority=5, release=True),
        builders.order("ORD-HI", qty=50, priority=1, release=True),
    )

    wms.create_orders(batch)

    assert wms.get_order("ORD-HI").json()["status"] == "RELEASED"
    assert wms.get_order("ORD-LO").json()["status"] == "NEW"
    assert wms.get_tasks(reference="ORD-LO").json() == []
    assert wms.get_stock(product).json() == {
        "productId": product, "onHand": 60, "allocated": 50, "available": 10,
    }


def test_batch_update_releases_orders_in_priority_order(wms, stocked_pallet):
    wms.create_orders(builders.order_batch(
        builders.order("ORD-A", qty=40),
        builders.order("ORD-B", qty=40),
    ))

    wms.update_orders({"order": [
        {"orderId": "ORD-A", "priority": 5, "orderRelease": True},
        {"orderId": "ORD-B", "priority": 1, "orderRelease": True},
    ]})

    assert wms.get_order("ORD-B").json()["status"] == "RELEASED"
    assert wms.get_order("ORD-A").json()["status"] == "NEW"


def test_equal_priority_orders_released_in_fifo_order(wms, stocked_pallet):
    batch = builders.order_batch(
        builders.order("ORD-FIRST", qty=40, priority=5, release=True),
        builders.order("ORD-SECOND", qty=40, priority=5, release=True),
    )

    wms.create_orders(batch)

    assert wms.get_order("ORD-FIRST").json()["status"] == "RELEASED"
    assert wms.get_order("ORD-SECOND").json()["status"] == "NEW"
