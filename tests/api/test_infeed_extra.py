import pytest
from framework import builders


def test_asn(wms, product, http):
    body = {"asnType": "Receipt", "owner": "DEMO",
            "transportUnit": {"tuId": "PAL-0009", "tuType": "EURO", "weight": 420.0},
            "asnLine": [{"lineNumber": 1, "productId": "SKU-100", "quantityExpected": 60}]}
    r = http.post("/interface/asns/asn-create", json=body)
    assert r.status_code == 201


def test_overweight_pallet(wms, product):
    wms.create_asn(builders.asn("PAL-0001", weight=420.0))
    r = wms.infeed_scan("PAL-0001", "EURO", 470.0)
    assert r.status_code == 201


def test_wrong_type_rejected(wms, product):
    wms.create_asn(builders.asn("PAL-0001", tu_type="EURO"))
    result = wms.infeed_scan("PAL-0001", "TOTE", 420.0).json()
    assert result["result"] == "NIO"
