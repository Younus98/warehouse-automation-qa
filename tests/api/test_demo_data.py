"""Demo data - the warehouse state used to show the screen must stay correct."""
from framework import builders


def test_demo_data_builds_the_expected_warehouse(wms):
    result = wms.load_demo_data().json()

    assert result == {"status": "LOADED", "products": 3, "transportUnits": 3, "orders": 3, "openTasks": 1}
    assert wms.get_stock("SKU-100").json() == {"productId": "SKU-100", "onHand": 60, "allocated": 24, "available": 36}
    nio = wms.get_transport_unit("PAL-0003").json()
    assert (nio["location"], nio["status"]) == ("NIO-01", "BLOCKED")
    assert wms.get_asn("PAL-0004").json()["status"] == "ANNOUNCED"
    assert [wms.get_order(o).json()["status"] for o in ("ORD-1001", "ORD-1002", "ORD-1003")] == [
        "RELEASED", "NEW", "NEW"]


def test_demo_data_replaces_existing_data(wms, product):
    wms.create_asn(builders.asn("PAL-9999"))

    wms.load_demo_data()

    assert wms.get_asn("PAL-9999").status_code == 404


def test_demo_order_on_blocked_stock_cannot_be_released(wms):
    wms.load_demo_data()

    response = wms.release_order("ORD-1003")

    assert response.status_code == 409
    assert wms.get_order("ORD-1003").json()["status"] == "NEW"
