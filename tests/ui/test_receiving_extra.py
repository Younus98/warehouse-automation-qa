import time
from framework import builders


def test_scan_from_ui(wms, product, wms_page, page):
    wms.create_asn(builders.asn("PAL-0001"))
    wms_page.open()
    page.click("text=Receiving")
    page.fill("input[name=tuId]", "PAL-0001")
    page.fill("input[name=weight]", "420")
    page.click(".action")
    time.sleep(2)
    assert "OK" in page.inner_text("#message")
