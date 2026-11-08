"""
WmsClient - one Python method per WMS endpoint.

Tests call wms.create_asn(...) instead of building URLs and HTTP calls
themselves. If an endpoint address changes, we fix it here once instead
of in every test.
"""


class WmsClient:
    def __init__(self, http):
        # http is any client with .get/.post (httpx.Client or FastAPI TestClient)
        self.http = http

    # --- Host interface (what SoapUI used to send) ---
    def create_product(self, body):
        return self.http.post("/interface/products/product-create", json=body)

    def create_asn(self, body):
        return self.http.post("/interface/asns/asn-create", json=body)

    def create_orders(self, body):
        return self.http.post("/interface/orders/batch-create", json=body)

    def update_orders(self, body):
        return self.http.post("/interface/orders/batch-update", json=body)

    def create_transport_order(self, body):
        return self.http.post("/interface/transport/orders-create", json=body)

    # --- WMS screens ---
    def infeed_scan(self, tu_id, tu_type, weight):
        return self.http.post("/api/receiving/infeed",
                              json={"tuId": tu_id, "tuType": tu_type, "weight": weight})

    def get_asn(self, tu_id):
        return self.http.get(f"/api/asns/{tu_id}")

    def get_transport_unit(self, tu_id):
        return self.http.get(f"/api/transport-units/{tu_id}")

    def get_stock(self, product_id):
        return self.http.get(f"/api/stock/{product_id}")

    def get_transactions(self, product_id=None):
        params = {"productId": product_id} if product_id else None
        return self.http.get("/api/inventory-transactions", params=params)

    def get_order(self, order_id):
        return self.http.get(f"/api/orders/{order_id}")

    def release_order(self, order_id):
        return self.http.post(f"/api/orders/{order_id}/release")

    def get_tasks(self, reference=None, status=None):
        params = {k: v for k, v in {"reference": reference, "status": status}.items() if v}
        return self.http.get("/api/tasks", params=params)

    def complete_task(self, task_id):
        return self.http.post(f"/api/tasks/{task_id}/complete")

    def load_demo_data(self):
        return self.http.post("/api/test/demo-data")

    def reset(self):
        return self.http.post("/api/test/reset")
