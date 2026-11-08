"""UI tests - the same business flows, checked the way a user sees them."""
import pytest
from playwright.sync_api import expect

from framework import builders


@pytest.mark.smoke
def test_scanning_matching_pallet_shows_ok_and_updates_stock(wms, product, wms_page):
    wms.create_asn(builders.asn("PAL-0001", weight=420.0, qty=60))
    wms_page.open()

    wms_page.scan_pallet("PAL-0001", "EURO", 425.0)

    expect(wms_page.message).to_have_text("Pallet PAL-0001 OK - stored at STORAGE-01")
    wms_page.expect_stock(product, on_hand=60, allocated=0, available=60)
    expect(wms_page.tu_row("PAL-0001").get_by_test_id("location")).to_have_text("STORAGE-01")


def test_scanning_overweight_pallet_shows_nio_reason(wms, product, wms_page):
    wms.create_asn(builders.asn("PAL-0001", weight=420.0))
    wms_page.open()

    wms_page.scan_pallet("PAL-0001", "EURO", 500.0)

    expect(wms_page.message).to_contain_text("NIO")
    expect(wms_page.message).to_contain_text("deviates 19.0%")
    wms_page.go_to("inventory")
    expect(wms_page.tu_row("PAL-0001").get_by_test_id("tu-status")).to_have_text("BLOCKED")


def test_scanning_pallet_without_asn_shows_error(wms, product, wms_page):
    wms_page.open()

    wms_page.scan_pallet("PAL-GHOST", "EURO", 420.0)

    expect(wms_page.message).to_have_text("No ASN for TU PAL-GHOST")


@pytest.mark.smoke
def test_release_order_from_order_planner(wms, stocked_pallet, product, wms_page):
    wms.create_orders(builders.order_batch(builders.order("ORD-1", qty=24)))
    wms_page.open()

    wms_page.release_order("ORD-1")

    expect(wms_page.message).to_have_text("Order ORD-1 released")
    expect(wms_page.order_row("ORD-1").get_by_test_id("order-status")).to_have_text("RELEASED")
    wms_page.expect_stock(product, on_hand=60, allocated=24, available=36)


def test_release_with_insufficient_stock_shows_error(wms, stocked_pallet, wms_page):
    wms.create_orders(builders.order_batch(builders.order("ORD-1", qty=100)))
    wms_page.open()

    wms_page.release_order("ORD-1")

    expect(wms_page.message).to_have_text("Insufficient stock for SKU-100: 60 available, 100 ordered")
    expect(wms_page.order_row("ORD-1").get_by_test_id("order-status")).to_have_text("NEW")


@pytest.mark.smoke
def test_complete_pick_task_removes_it_and_reduces_stock(wms, stocked_pallet, product, wms_page):
    wms.create_orders(builders.order_batch(builders.order("ORD-1", qty=24, release=True)))
    task_id = wms.get_tasks(reference="ORD-1").json()[0]["taskId"]
    wms_page.open()

    wms_page.complete_task(task_id)

    expect(wms_page.message).to_have_text(f"Task {task_id} completed")
    expect(wms_page.task_rows()).to_have_count(0)
    wms_page.expect_stock(product, on_hand=36, allocated=0, available=36)
    wms_page.go_to("orders")
    expect(wms_page.order_row("ORD-1").get_by_test_id("order-status")).to_have_text("PICKED")


def test_load_demo_data_button_fills_the_screen(wms, wms_page):
    wms_page.open()

    wms_page.load_demo_data()

    expect(wms_page.message).to_have_text("Demo data loaded: 3 products, 3 pallets, 3 orders, 1 open task")
    wms_page.expect_stock("SKU-100", on_hand=60, allocated=24, available=36)
    expect(wms_page.tu_row("PAL-0003").get_by_test_id("tu-status")).to_have_text("BLOCKED")
