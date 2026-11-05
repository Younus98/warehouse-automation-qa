"""
Mini WMS (Warehouse Management System) - the system under test.

A deliberately simple warehouse system that mirrors a real WMS:
- REST/JSON endpoints (/api/...) are what the screens use.
- XML interface endpoints (/interface/...) are how a host system (ERP)
  sends messages such as orders - the kind of request a tester sends
  from SoapUI.

All data lives in memory, so every restart starts from a clean warehouse.
"""

from fastapi import FastAPI, HTTPException, Request, Response
from lxml import etree
from pydantic import BaseModel, Field

app = FastAPI(title="Mini WMS", version="0.1.0")

# ---------------------------------------------------------------------------
# In-memory "database"
# ---------------------------------------------------------------------------
products: dict[str, dict] = {}  # key: SKU
orders: dict[str, dict] = {}    # key: order number


# ---------------------------------------------------------------------------
# Master Data > Products  (JSON)
# ---------------------------------------------------------------------------
class ProductIn(BaseModel):
    sku: str = Field(min_length=1, max_length=20)
    description: str = Field(min_length=1, max_length=100)
    weight_kg: float = Field(gt=0)


@app.post("/api/products", status_code=201)
def create_product(product: ProductIn):
    if product.sku in products:
        raise HTTPException(status_code=409, detail=f"Product {product.sku} already exists")
    products[product.sku] = product.model_dump()
    return products[product.sku]


@app.get("/api/products")
def list_products():
    return list(products.values())


@app.get("/api/products/{sku}")
def get_product(sku: str):
    if sku not in products:
        raise HTTPException(status_code=404, detail=f"Product {sku} not found")
    return products[sku]


# ---------------------------------------------------------------------------
# Host interface > Order  (XML in, XML out - like a SoapUI request)
# ---------------------------------------------------------------------------
def xml_ack(status: str, order_number: str, message: str, http_status: int) -> Response:
    """Build the XML acknowledgement the WMS sends back to the host."""
    ack = etree.Element("OrderAck")
    etree.SubElement(ack, "OrderNumber").text = order_number
    etree.SubElement(ack, "Status").text = status
    etree.SubElement(ack, "Message").text = message
    body = etree.tostring(ack, xml_declaration=True, encoding="UTF-8", pretty_print=True)
    return Response(content=body, media_type="application/xml", status_code=http_status)


@app.post("/interface/orders")
async def receive_order(request: Request):
    raw = await request.body()

    # 1. Is it well-formed XML?
    try:
        root = etree.fromstring(raw)
    except etree.XMLSyntaxError:
        return xml_ack("REJECTED", "", "Malformed XML", 400)

    # 2. Read the header fields with XPath
    order_number = root.findtext("OrderNumber", default="").strip()
    customer = root.findtext("Customer", default="").strip()
    if not order_number or not customer:
        return xml_ack("REJECTED", order_number, "OrderNumber and Customer are required", 400)
    if order_number in orders:
        return xml_ack("REJECTED", order_number, "Duplicate order number", 409)

    # 3. Validate every order line
    lines = []
    for line in root.xpath("./Lines/Line"):
        sku = line.findtext("Sku", default="").strip()
        qty_text = line.findtext("Quantity", default="").strip()
        if sku not in products:
            return xml_ack("REJECTED", order_number, f"Unknown product {sku}", 422)
        if not qty_text.isdigit() or int(qty_text) <= 0:
            return xml_ack("REJECTED", order_number, f"Invalid quantity for {sku}", 422)
        lines.append({"sku": sku, "quantity": int(qty_text)})

    if not lines:
        return xml_ack("REJECTED", order_number, "Order has no lines", 422)

    # 4. Store the order - it starts in status NEW
    orders[order_number] = {
        "order_number": order_number,
        "customer": customer,
        "status": "NEW",
        "lines": lines,
    }
    return xml_ack("ACCEPTED", order_number, "Order received", 201)


# ---------------------------------------------------------------------------
# Orders  (JSON view, like the Orders screen)
# ---------------------------------------------------------------------------
@app.get("/api/orders/{order_number}")
def get_order(order_number: str):
    if order_number not in orders:
        raise HTTPException(status_code=404, detail=f"Order {order_number} not found")
    return orders[order_number]


# ---------------------------------------------------------------------------
# Test helper - wipe all data so each test starts clean
# ---------------------------------------------------------------------------
@app.post("/api/test/reset", status_code=204)
def reset():
    products.clear()
    orders.clear()
