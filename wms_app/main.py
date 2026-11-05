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
transport_units: dict[str, dict] = {}  # key: TU id (pallet / tote barcode)
inventory_transactions: list[dict] = []  # append-only audit trail


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
# Warehouse Management > Inventory
#   Transport Unit (TU) = the physical carrier: a pallet or a tote
#   Load Unit (LU)      = the stock inside a TU: one product + a quantity
#   Inventory Transaction = an audit-trail entry for every stock change
# ---------------------------------------------------------------------------
TU_TYPES = {"PALLET", "TOTE"}


class TransportUnitIn(BaseModel):
    tu_id: str = Field(min_length=1, max_length=20)
    tu_type: str
    location: str = Field(min_length=1, max_length=20)


class LoadUnitIn(BaseModel):
    sku: str
    quantity: int = Field(gt=0)


def book_transaction(tx_type: str, sku: str, quantity: int, tu_id: str, reference: str = "") -> dict:
    """Record a stock movement. RECEIPT adds stock, PICK removes it."""
    tx = {
        "tx_id": len(inventory_transactions) + 1,
        "type": tx_type,
        "sku": sku,
        "quantity": quantity,
        "tu_id": tu_id,
        "reference": reference,
    }
    inventory_transactions.append(tx)
    return tx


@app.post("/api/transport-units", status_code=201)
def create_transport_unit(tu: TransportUnitIn):
    if tu.tu_type not in TU_TYPES:
        raise HTTPException(status_code=422, detail=f"tu_type must be one of {sorted(TU_TYPES)}")
    if tu.tu_id in transport_units:
        raise HTTPException(status_code=409, detail=f"Transport unit {tu.tu_id} already exists")
    transport_units[tu.tu_id] = {**tu.model_dump(), "load_units": []}
    return transport_units[tu.tu_id]


@app.get("/api/transport-units/{tu_id}")
def get_transport_unit(tu_id: str):
    if tu_id not in transport_units:
        raise HTTPException(status_code=404, detail=f"Transport unit {tu_id} not found")
    return transport_units[tu_id]


@app.post("/api/transport-units/{tu_id}/load-units", status_code=201)
def add_load_unit(tu_id: str, lu: LoadUnitIn):
    """Put stock onto a transport unit - this is a goods receipt."""
    if tu_id not in transport_units:
        raise HTTPException(status_code=404, detail=f"Transport unit {tu_id} not found")
    if lu.sku not in products:
        raise HTTPException(status_code=422, detail=f"Unknown product {lu.sku}")

    tu = transport_units[tu_id]
    load_unit = {"lu_id": f"{tu_id}-LU{len(tu['load_units']) + 1}", **lu.model_dump()}
    tu["load_units"].append(load_unit)
    book_transaction("RECEIPT", lu.sku, lu.quantity, tu_id)
    return load_unit


@app.get("/api/inventory-transactions")
def list_inventory_transactions(sku: str | None = None):
    if sku:
        return [tx for tx in inventory_transactions if tx["sku"] == sku]
    return inventory_transactions


@app.get("/api/stock/{sku}")
def get_stock(sku: str):
    """Total quantity of a product across all transport units."""
    if sku not in products:
        raise HTTPException(status_code=404, detail=f"Product {sku} not found")
    total = sum(
        lu["quantity"]
        for tu in transport_units.values()
        for lu in tu["load_units"]
        if lu["sku"] == sku
    )
    return {"sku": sku, "quantity": total}


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
    transport_units.clear()
    inventory_transactions.clear()
