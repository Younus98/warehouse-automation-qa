"""
UI test setup.

Starts the Mini WMS as a real web server (in a background thread) so the
browser has something to open. Test data is created through the API -
that's fast and reliable - and the UI is used only for what the test is
actually about.
"""
import socket
import threading
import time

import httpx
import pytest
import uvicorn

from framework.pages.wms_page import WmsPage
from wms_app.main import app


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def base_url():
    """Used by pytest-playwright: page.goto('/') opens this address."""
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join()


@pytest.fixture(scope="session")
def http(base_url):
    """API setup calls go to the same server the browser uses."""
    with httpx.Client(base_url=base_url, timeout=10) as client:
        yield client


@pytest.fixture
def wms_page(page, wms) -> WmsPage:
    """Depends on `wms`, so the warehouse is reset before the browser opens."""
    return WmsPage(page)
