"""
Mini WMS (Warehouse Management System) - the system under test.

A deliberately simple warehouse system modelled on a real automated warehouse:

  /interface/...  Host interface. The customer's ERP sends JSON messages here
                  (products, ASNs, orders, transport orders) - the kind of
                  request a tester sends from SoapUI.
  /api/...        What the WMS screens use: inventory, receiving, order
                  planner, tasks.

Business flow:
  ASN announces a pallet -> pallet arrives at infeed -> ASN check
    -> OK: stock booked into storage      -> NOK: pallet sent to NiO
  Order received -> Order Planner releases it -> stock allocated
    -> PICK tasks created -> tasks completed -> stock reduced -> order PICKED

All data lives in memory, so every restart starts with an empty warehouse.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

app = FastAPI(title="Mini WMS", version="0.2.0")

# ---------------------------------------------------------------------------
# Warehouse settings
# ---------------------------------------------------------------------------
TU_TYPES = {"EURO", "INDU", "TOTE"}  # Euro pallet, industrial pallet, plastic tote
STORAGE_LOCATION = "STORAGE-01"      # where good pallets go after the ASN check
NIO_LOCATION = "NIO-01"              # "nicht in Ordnung": reject / clarification point
WEIGHT_TOLERANCE = 0.05              # ASN check allows +/- 5 % weight difference

# ---------------------------------------------------------------------------
# In-memory "database"
# ---------------------------------------------------------------------------
products: dict[str, dict] = {}           # key: productId
asns: dict[str, dict] = {}               # key: tuId (one ASN announces one TU)
transport_units: dict[str, dict] = {}    # key: tuId
inventory_transactions: list[dict] = []  # append-only audit trail
orders: dict[str, dict] = {}             # key: orderId
tasks: dict[int, dict] = {}              # key: taskId
transport_orders: dict[int, dict] = {}   # key: transportOrderId


def not_found(what: str, key) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{what} {key} not found")


def book_transaction(tx_type: str, product_id: str, quantity: float, tu_id: str, reference: str) -> None:
    """Record a stock movement. RECEIPT adds stock, PICK removes it."""
    inventory_transactions.append({
        "txId": len(inventory_transactions) + 1,
        "type": tx_type,
        "productId": product_id,
        "quantity": quantity,
        "tuId": tu_id,
        "reference": reference,
    })


# ===========================================================================
# HOST INTERFACE (JSON messages from the ERP)
# ===========================================================================

# --- Master Data > Products -------------------------------------------------
class ProductCreate(BaseModel):
    productId: str = Field(min_length=1, max_length=20)
    owner: str = Field(min_length=1)
    description: str = Field(min_length=1, max_length=100)


@app.post("/interface/products/product-create", status_code=201)
def product_create(msg: ProductCreate):
    if msg.productId in products:
        raise HTTPException(status_code=409, detail=f"Product {msg.productId} already exists")
    products[msg.productId] = msg.model_dump()
    return {"status": "ACCEPTED", "productId": msg.productId}


# --- Receiving > Advance Shipping Notice ------------------------------------
class AsnTransportUnit(BaseModel):
    tuId: str = Field(min_length=1, max_length=20)
    tuType: str
    weight: float = Field(gt=0)  # kg


class AsnLine(BaseModel):
    lineNumber: int = Field(gt=0)
    productId: str
    quantityExpected: float = Field(gt=0)


class AsnCreate(BaseModel):
    asnType: str = "Receipt"
    owner: str = Field(min_length=1)
    transportUnit: AsnTransportUnit
    asnLine: list[AsnLine] = Field(min_length=1)


@app.post("/interface/asns/asn-create", status_code=201)
def asn_create(msg: AsnCreate):
    tu = msg.transportUnit
    if tu.tuType not in TU_TYPES:
        raise HTTPException(status_code=422, detail=f"tuType must be one of {sorted(TU_TYPES)}")
    if tu.tuId in asns or tu.tuId in transport_units:
        raise HTTPException(status_code=409, detail=f"TU {tu.tuId} is already announced or in stock")
    for line in msg.asnLine:
        if line.productId not in products:
            raise HTTPException(status_code=422, detail=f"Unknown product {line.productId}")

    asns[tu.tuId] = {**msg.model_dump(), "status": "ANNOUNCED"}
    return {"status": "ACCEPTED", "tuId": tu.tuId}


# --- Orders -----------------------------------------------------------------
class OrderLine(BaseModel):
    orderLineNumber: int = Field(gt=0)
    productId: str
    quantityOrdered: float = Field(gt=0)


class Order(BaseModel):
    orderId: str = Field(min_length=1, max_length=30)
    owner: str = Field(min_length=1)
    orderType: str = "NORMAL"
    priority: int = Field(default=5, ge=1, le=9)
    shortAllocationAllowed: bool = False
    orderRelease: bool = False
    orderLine: list[OrderLine] = Field(min_length=1)


class OrderBatch(BaseModel):
    order: list[Order] = Field(min_length=1)


@app.post("/interface/orders/batch-create")
def order_batch_create(batch: OrderBatch):
    """Each order in the batch is checked on its own; one bad order doesn't block the rest."""
    results = []
    for o in batch.order:
        if o.orderId in orders:
            results.append({"orderId": o.orderId, "status": "REJECTED", "message": "Duplicate orderId"})
            continue
        unknown = [l.productId for l in o.orderLine if l.productId not in products]
        if unknown:
            results.append({"orderId": o.orderId, "status": "REJECTED", "message": f"Unknown product {unknown[0]}"})
            continue

        orders[o.orderId] = {**o.model_dump(), "status": "NEW"}
        result = {"orderId": o.orderId, "status": "ACCEPTED", "message": "Order received"}
        if o.orderRelease:  # host asked for immediate release
            try:
                release_order(o.orderId)
                result["message"] = "Order received and released"
            except HTTPException as err:
                result["message"] = f"Order received, release failed: {err.detail}"
        results.append(result)
    return {"results": results}


class OrderUpdate(BaseModel):
    orderId: str
    priority: int | None = Field(default=None, ge=1, le=9)
    orderRelease: bool = False


class OrderUpdateBatch(BaseModel):
    order: list[OrderUpdate] = Field(min_length=1)


@app.post("/interface/orders/batch-update")
def order_batch_update(batch: OrderUpdateBatch):
    """Change priority and/or release orders - the host's way of driving the Order Planner."""
    results = []
    for u in batch.order:
        if u.orderId not in orders:
            results.append({"orderId": u.orderId, "status": "REJECTED", "message": "Order not found"})
            continue
        if u.priority is not None:
            orders[u.orderId]["priority"] = u.priority
        message = "Order updated"
        if u.orderRelease:
            try:
                release_order(u.orderId)
                message = "Order released"
            except HTTPException as err:
                results.append({"orderId": u.orderId, "status": "REJECTED", "message": err.detail})
                continue
        results.append({"orderId": u.orderId, "status": "ACCEPTED", "message": message})
    return {"results": results}


# --- Transport orders -------------------------------------------------------
class TransportOrderCreate(BaseModel):
    tuId: str
    sourceLocation: str = Field(min_length=1)
    destinationLocation: str = Field(min_length=1)
    priority: int = Field(default=5, ge=1, le=9)


@app.post("/interface/transport/orders-create", status_code=201)
def transport_order_create(msg: TransportOrderCreate):
    """Move a pallet from one location to another. Creates a MOVE task."""
    if msg.tuId not in transport_units:
        raise not_found("Transport unit", msg.tuId)
    tu = transport_units[msg.tuId]
    if tu["location"] != msg.sourceLocation:
        raise HTTPException(status_code=409,
                            detail=f"TU {msg.tuId} is at {tu['location']}, not at {msg.sourceLocation}")
    if msg.sourceLocation == msg.destinationLocation:
        raise HTTPException(status_code=422, detail="Source and destination are the same")
    if any(t["tuId"] == msg.tuId and t["status"] == "OPEN" for t in tasks.values()):
        raise HTTPException(status_code=409, detail=f"TU {msg.tuId} already has an open task")

    to_id = len(transport_orders) + 1
    transport_orders[to_id] = {**msg.model_dump(), "transportOrderId": to_id, "status": "OPEN"}
    task = create_task("MOVE", tu_id=msg.tuId, destination=msg.destinationLocation,
                       reference=f"TO-{to_id}")
    return {"status": "ACCEPTED", "transportOrderId": to_id, "taskId": task["taskId"]}


# ===========================================================================
# WMS SCREENS
# ===========================================================================

# --- Master Data > Products -------------------------------------------------
@app.get("/api/products")
def list_products():
    return list(products.values())


@app.get("/api/products/{product_id}")
def get_product(product_id: str):
    if product_id not in products:
        raise not_found("Product", product_id)
    return products[product_id]


# --- Receiving > ASN + infeed ASN check -------------------------------------
@app.get("/api/asns/{tu_id}")
def get_asn(tu_id: str):
    if tu_id not in asns:
        raise not_found("ASN for TU", tu_id)
    return asns[tu_id]


class InfeedScan(BaseModel):
    tuId: str
    tuType: str
    weight: float = Field(gt=0)  # what the infeed scale measured


@app.post("/api/receiving/infeed", status_code=201)
def infeed_scan(scan: InfeedScan):
    """
    A pallet arrives at the infeed conveyor. The WMS compares it with its ASN:
      - TU type must match
      - weight must be within +/- 5 % of the announced weight
    OK  -> TU created in storage, stock booked (RECEIPT per ASN line)
    NOK -> TU created at the NiO location, blocked, no stock booked
    """
    if scan.tuId not in asns:
        raise HTTPException(status_code=422, detail=f"No ASN for TU {scan.tuId}")
    asn = asns[scan.tuId]
    if asn["status"] != "ANNOUNCED":
        raise HTTPException(status_code=409, detail=f"ASN for TU {scan.tuId} is already {asn['status']}")

    expected = asn["transportUnit"]
    reasons = []
    if scan.tuType != expected["tuType"]:
        reasons.append(f"TU type {scan.tuType} does not match ASN {expected['tuType']}")
    deviation = abs(scan.weight - expected["weight"]) / expected["weight"]
    if deviation > WEIGHT_TOLERANCE:
        reasons.append(f"Weight {scan.weight} kg deviates {deviation:.1%} from ASN {expected['weight']} kg")

    load_units = [
        {"luId": f"{scan.tuId}-LU{line['lineNumber']}",
         "productId": line["productId"],
         "quantity": line["quantityExpected"]}
        for line in asn["asnLine"]
    ]

    if reasons:
        transport_units[scan.tuId] = {"tuId": scan.tuId, "tuType": scan.tuType,
                                      "location": NIO_LOCATION, "status": "BLOCKED",
                                      "loadUnits": load_units}
        asn["status"] = "NIO"
        return {"result": "NIO", "location": NIO_LOCATION, "reasons": reasons}

    transport_units[scan.tuId] = {"tuId": scan.tuId, "tuType": scan.tuType,
                                  "location": STORAGE_LOCATION, "status": "AVAILABLE",
                                  "loadUnits": load_units}
    for lu in load_units:
        book_transaction("RECEIPT", lu["productId"], lu["quantity"], scan.tuId, reference=f"ASN-{scan.tuId}")
    asn["status"] = "RECEIVED"
    return {"result": "OK", "location": STORAGE_LOCATION, "reasons": []}


# --- Warehouse Management > Inventory ---------------------------------------
@app.get("/api/transport-units/{tu_id}")
def get_transport_unit(tu_id: str):
    if tu_id not in transport_units:
        raise not_found("Transport unit", tu_id)
    return transport_units[tu_id]


@app.get("/api/inventory-transactions")
def list_inventory_transactions(productId: str | None = None):
    if productId:
        return [tx for tx in inventory_transactions if tx["productId"] == productId]
    return inventory_transactions


def on_hand(product_id: str) -> float:
    """Physical stock on all pallets in the warehouse."""
    return sum(lu["quantity"]
               for tu in transport_units.values()
               for lu in tu["loadUnits"] if lu["productId"] == product_id)


def allocated(product_id: str) -> float:
    """Stock already reserved by open PICK tasks."""
    return sum(t["quantity"] for t in tasks.values()
               if t["type"] == "PICK" and t["status"] == "OPEN" and t["productId"] == product_id)


@app.get("/api/stock/{product_id}")
def get_stock(product_id: str):
    if product_id not in products:
        raise not_found("Product", product_id)
    total = on_hand(product_id)
    reserved = allocated(product_id)
    return {"productId": product_id, "onHand": total, "allocated": reserved, "available": total - reserved}


# --- Orders > Order Planner -------------------------------------------------
@app.get("/api/orders/{order_id}")
def get_order(order_id: str):
    if order_id not in orders:
        raise not_found("Order", order_id)
    return orders[order_id]


@app.post("/api/orders/{order_id}/release")
def release_order(order_id: str):
    """
    Release an order: allocate stock and create one PICK task per pallet used.
    - Not enough stock and shortAllocationAllowed = False -> release refused
    - Not enough stock and shortAllocationAllowed = True  -> allocate what exists
    """
    if order_id not in orders:
        raise not_found("Order", order_id)
    order = orders[order_id]
    if order["status"] != "NEW":
        raise HTTPException(status_code=409, detail=f"Order {order_id} is already {order['status']}")

    # 1. Check stock for every line before creating anything
    for line in order["orderLine"]:
        free = on_hand(line["productId"]) - allocated(line["productId"])
        if free < line["quantityOrdered"] and not order["shortAllocationAllowed"]:
            raise HTTPException(status_code=409,
                                detail=f"Insufficient stock for {line['productId']}: "
                                       f"{free:g} available, {line['quantityOrdered']:g} ordered")
        if free <= 0:
            raise HTTPException(status_code=409, detail=f"No stock for {line['productId']}")

    # 2. Allocate pallet by pallet (oldest pallet first) and create PICK tasks
    for line in order["orderLine"]:
        still_needed = line["quantityOrdered"]
        for tu in transport_units.values():
            if still_needed <= 0:
                break
            if tu["status"] != "AVAILABLE":
                continue
            for lu in tu["loadUnits"]:
                if lu["productId"] != line["productId"]:
                    continue
                reserved_here = sum(t["quantity"] for t in tasks.values()
                                    if t["status"] == "OPEN" and t["luId"] == lu["luId"])
                take = min(lu["quantity"] - reserved_here, still_needed)
                if take > 0:
                    create_task("PICK", tu_id=tu["tuId"], lu_id=lu["luId"],
                                product_id=lu["productId"], quantity=take, reference=order_id)
                    still_needed -= take
        line["quantityAllocated"] = line["quantityOrdered"] - still_needed

    order["status"] = "RELEASED"
    return order


# --- Operations > Task ------------------------------------------------------
def create_task(task_type: str, tu_id: str, reference: str, lu_id: str | None = None,
                product_id: str | None = None, quantity: float = 0,
                destination: str | None = None) -> dict:
    task_id = len(tasks) + 1
    tasks[task_id] = {
        "taskId": task_id, "type": task_type, "status": "OPEN", "reference": reference,
        "tuId": tu_id, "luId": lu_id, "productId": product_id, "quantity": quantity,
        "destination": destination,
    }
    return tasks[task_id]


@app.get("/api/tasks")
def list_tasks(status: str | None = None, reference: str | None = None):
    result = list(tasks.values())
    if status:
        result = [t for t in result if t["status"] == status]
    if reference:
        result = [t for t in result if t["reference"] == reference]
    return result


@app.post("/api/tasks/{task_id}/complete")
def complete_task(task_id: int):
    """
    PICK: take the quantity off the load unit, book a PICK transaction,
          and mark the order PICKED once all its tasks are done.
    MOVE: move the pallet to its destination and close the transport order.
    """
    if task_id not in tasks:
        raise not_found("Task", task_id)
    task = tasks[task_id]
    if task["status"] != "OPEN":
        raise HTTPException(status_code=409, detail=f"Task {task_id} is already {task['status']}")

    tu = transport_units[task["tuId"]]
    if task["type"] == "PICK":
        lu = next(lu for lu in tu["loadUnits"] if lu["luId"] == task["luId"])
        lu["quantity"] -= task["quantity"]
        if lu["quantity"] == 0:
            tu["loadUnits"].remove(lu)
        book_transaction("PICK", task["productId"], -task["quantity"], tu["tuId"], reference=task["reference"])
        task["status"] = "DONE"
        order = orders[task["reference"]]
        if all(t["status"] == "DONE" for t in tasks.values() if t["reference"] == order["orderId"]):
            order["status"] = "PICKED"
    else:  # MOVE
        tu["location"] = task["destination"]
        task["status"] = "DONE"
        transport_orders[int(task["reference"].removeprefix("TO-"))]["status"] = "DONE"

    return task


# ---------------------------------------------------------------------------
# Lists for the screen + the screen itself
# ---------------------------------------------------------------------------
@app.get("/api/transport-units")
def list_transport_units():
    return list(transport_units.values())


@app.get("/api/orders")
def list_orders():
    return list(orders.values())


@app.get("/api/stock")
def list_stock():
    return [get_stock(product_id) for product_id in products]


@app.get("/", include_in_schema=False)
def screen():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


# ---------------------------------------------------------------------------
# Test helper - wipe all data so each test starts with an empty warehouse
# ---------------------------------------------------------------------------
@app.post("/api/test/reset", status_code=204)
def reset():
    for store in (products, asns, transport_units, inventory_transactions,
                  orders, tasks, transport_orders):
        store.clear()
