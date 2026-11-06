"""
Test data builders - a valid message by default, change only what the test is about.

    asn(tu_id="PAL-1", weight=500)      -> a full valid ASN with those two values changed
    order("ORD-1", qty=24)              -> a full valid order for 24 units

This keeps every test short and makes it obvious which field the test checks.
"""

DEFAULT_PRODUCT = "SKU-100"
OWNER = "DEMO"


def product(product_id=DEFAULT_PRODUCT, description="Mineral water 6x1.5L", owner=OWNER):
    return {"productId": product_id, "owner": owner, "description": description}


def asn(tu_id="PAL-0001", tu_type="EURO", weight=420.0, product_id=DEFAULT_PRODUCT, qty=60, lines=None):
    return {
        "asnType": "Receipt",
        "owner": OWNER,
        "transportUnit": {"tuId": tu_id, "tuType": tu_type, "weight": weight},
        "asnLine": lines if lines is not None else [
            {"lineNumber": 1, "productId": product_id, "quantityExpected": qty}
        ],
    }


def order(order_id="ORD-1001", product_id=DEFAULT_PRODUCT, qty=24,
          short_allocation=False, release=False, priority=5):
    return {
        "orderId": order_id,
        "owner": OWNER,
        "orderType": "NORMAL",
        "priority": priority,
        "shortAllocationAllowed": short_allocation,
        "orderRelease": release,
        "orderLine": [{"orderLineNumber": 1, "productId": product_id, "quantityOrdered": qty}],
    }


def order_batch(*orders):
    return {"order": list(orders)}


def transport_order(tu_id="PAL-0001", source="STORAGE-01", destination="PICK-STATION-1"):
    return {"tuId": tu_id, "sourceLocation": source, "destinationLocation": destination, "priority": 5}
