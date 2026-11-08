"""Receiving - ASN from the host, then the ASN check at the infeed."""
import pytest

from framework import builders


# --- ASN interface ----------------------------------------------------------
@pytest.mark.smoke
def test_asn_is_accepted_and_announced(wms, product):
    response = wms.create_asn(builders.asn("PAL-0001"))

    assert response.status_code == 201
    assert wms.get_asn("PAL-0001").json()["status"] == "ANNOUNCED"


@pytest.mark.negative
def test_asn_for_unknown_product_is_rejected(wms, product):
    response = wms.create_asn(builders.asn(product_id="SKU-DOES-NOT-EXIST"))

    assert response.status_code == 422
    assert "Unknown product" in response.json()["detail"]


@pytest.mark.negative
def test_duplicate_asn_for_same_tu_is_rejected(wms, product):
    wms.create_asn(builders.asn("PAL-0001"))

    response = wms.create_asn(builders.asn("PAL-0001"))

    assert response.status_code == 409


@pytest.mark.negative
@pytest.mark.parametrize("changes", [
    {"tu_type": "BOX"},   # not a known TU type
    {"weight": 0},        # weight must be > 0
    {"qty": 0},           # quantity must be > 0
    {"lines": []},        # ASN without lines
], ids=["unknown-tu-type", "zero-weight", "zero-quantity", "no-lines"])
def test_invalid_asn_is_rejected(wms, product, changes):
    response = wms.create_asn(builders.asn(**changes))

    assert response.status_code == 422


# --- Infeed ASN check -------------------------------------------------------
@pytest.mark.smoke
def test_matching_pallet_goes_to_storage_and_stock_is_booked(wms, product):
    wms.create_asn(builders.asn("PAL-0001", weight=420.0, qty=60))

    result = wms.infeed_scan("PAL-0001", "EURO", 420.0).json()

    assert result["result"] == "OK"
    assert wms.get_transport_unit("PAL-0001").json()["location"] == "STORAGE-01"
    assert wms.get_stock(product).json()["onHand"] == 60
    assert wms.get_asn("PAL-0001").json()["status"] == "RECEIVED"

    receipts = wms.get_transactions(product).json()
    assert [(t["type"], t["quantity"]) for t in receipts] == [("RECEIPT", 60)]


@pytest.mark.negative
def test_wrong_tu_type_goes_to_nio(wms, product):
    wms.create_asn(builders.asn("PAL-0001", tu_type="EURO"))

    result = wms.infeed_scan("PAL-0001", "INDU", 420.0).json()

    assert result["result"] == "NIO"
    assert "TU type INDU does not match ASN EURO" in result["reasons"]


# Boundary test for the +/- 5 % weight tolerance on a 420 kg pallet (5 % = 21 kg)
@pytest.mark.parametrize("scale_weight, expected", [
    (399.0, "OK"),    # -5.0 %  lower edge, still OK
    (398.9, "NIO"),   # just under the lower edge
    (441.0, "OK"),    # +5.0 %  upper edge, still OK
    (441.1, "NIO"),   # just over the upper edge
    (420.0, "OK"),    # exactly the ASN weight
])
def test_weight_tolerance_boundaries(wms, product, scale_weight, expected):
    wms.create_asn(builders.asn("PAL-0001", weight=420.0))

    result = wms.infeed_scan("PAL-0001", "EURO", scale_weight).json()

    assert result["result"] == expected


def test_nio_pallet_is_blocked_and_adds_no_stock(wms, product):
    wms.create_asn(builders.asn("PAL-0001", weight=420.0))

    wms.infeed_scan("PAL-0001", "EURO", 500.0)

    tu = wms.get_transport_unit("PAL-0001").json()
    assert (tu["location"], tu["status"]) == ("NIO-01", "BLOCKED")
    assert wms.get_stock(product).json()["onHand"] == 0
    assert wms.get_transactions(product).json() == []


@pytest.mark.negative
def test_pallet_without_asn_is_refused(wms, product):
    response = wms.infeed_scan("PAL-UNKNOWN", "EURO", 420.0)

    assert response.status_code == 422


@pytest.mark.negative
def test_same_pallet_cannot_be_received_twice(wms, stocked_pallet):
    response = wms.infeed_scan(stocked_pallet, "EURO", 420.0)

    assert response.status_code == 409
