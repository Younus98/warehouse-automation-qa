"""Operations > Task, and transport orders (pallet movements)."""
import pytest

from framework import builders


@pytest.fixture
def released_order(wms, stocked_pallet):
    """ORD-1 for 24 units is released, so one PICK task is open."""
    wms.create_orders(builders.order_batch(builders.order("ORD-1", qty=24, release=True)))
    return "ORD-1"


# --- Pick tasks -------------------------------------------------------------
@pytest.mark.smoke
def test_completing_pick_reduces_stock_and_finishes_order(wms, released_order, product):
    task = wms.get_tasks(reference=released_order).json()[0]

    response = wms.complete_task(task["taskId"])

    assert response.json()["status"] == "DONE"
    assert wms.get_order(released_order).json()["status"] == "PICKED"
    assert wms.get_stock(product).json() == {"productId": product, "onHand": 36, "allocated": 0, "available": 36}
    assert [(t["type"], t["quantity"]) for t in wms.get_transactions(product).json()] == [
        ("RECEIPT", 60), ("PICK", -24)]


@pytest.mark.negative
def test_task_cannot_be_completed_twice(wms, released_order, product):
    task_id = wms.get_tasks(reference=released_order).json()[0]["taskId"]
    wms.complete_task(task_id)

    response = wms.complete_task(task_id)

    assert response.status_code == 409
    assert wms.get_stock(product).json()["onHand"] == 36  # stock not reduced a second time


@pytest.mark.negative
def test_unknown_task_returns_404(wms):
    assert wms.complete_task(999).status_code == 404


# --- Transport orders -------------------------------------------------------
@pytest.mark.smoke
def test_transport_order_moves_pallet(wms, stocked_pallet):
    response = wms.create_transport_order(builders.transport_order(stocked_pallet, destination="PICK-STATION-1"))
    assert response.status_code == 201

    wms.complete_task(response.json()["taskId"])

    assert wms.get_transport_unit(stocked_pallet).json()["location"] == "PICK-STATION-1"


@pytest.mark.negative
def test_transport_order_with_wrong_source_is_refused(wms, stocked_pallet):
    response = wms.create_transport_order(builders.transport_order(stocked_pallet, source="AISLE-99"))

    assert response.status_code == 409


@pytest.mark.negative
def test_transport_order_with_same_source_and_destination_is_refused(wms, stocked_pallet):
    response = wms.create_transport_order(
        builders.transport_order(stocked_pallet, source="STORAGE-01", destination="STORAGE-01"))

    assert response.status_code == 422


@pytest.mark.negative
def test_pallet_with_open_pick_task_cannot_be_moved(wms, released_order, stocked_pallet):
    response = wms.create_transport_order(builders.transport_order(stocked_pallet))

    assert response.status_code == 409
    assert "already has an open task" in response.json()["detail"]


@pytest.mark.negative
def test_transport_order_for_unknown_pallet_returns_404(wms):
    assert wms.create_transport_order(builders.transport_order("PAL-GHOST")).status_code == 404
