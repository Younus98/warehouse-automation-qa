"""
Shared pytest fixtures.

By default the tests start the WMS inside the test process (fast, no server needed).
Set WMS_BASE_URL to test a running server instead, e.g.
    WMS_BASE_URL=http://localhost:8000 pytest
"""
import os

import httpx
import pytest
from fastapi.testclient import TestClient

from framework import builders
from framework.wms_client import WmsClient
from wms_app.main import app


@pytest.fixture(scope="session")
def http():
    base_url = os.getenv("WMS_BASE_URL")
    if base_url:
        with httpx.Client(base_url=base_url, timeout=10) as client:
            yield client
    else:
        with TestClient(app) as client:
            yield client


@pytest.fixture
def wms(http):
    """A WMS client on an empty warehouse - every test starts clean."""
    client = WmsClient(http)
    client.reset()
    return client


@pytest.fixture
def product(wms):
    """Product SKU-100 exists in master data."""
    assert wms.create_product(builders.product()).status_code == 201
    return builders.DEFAULT_PRODUCT


@pytest.fixture
def stocked_pallet(wms, product):
    """Pallet PAL-0001 with 60 x SKU-100 is received and in storage."""
    assert wms.create_asn(builders.asn()).status_code == 201
    assert wms.infeed_scan("PAL-0001", "EURO", 420.0).json()["result"] == "OK"
    return "PAL-0001"
