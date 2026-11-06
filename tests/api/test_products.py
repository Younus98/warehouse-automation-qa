"""Master Data > Products - created through the host interface."""
import pytest

from framework import builders


@pytest.mark.smoke
def test_create_product(wms):
    response = wms.create_product(builders.product("SKU-200"))

    assert response.status_code == 201
    assert response.json() == {"status": "ACCEPTED", "productId": "SKU-200"}


@pytest.mark.negative
def test_duplicate_product_is_rejected(wms, product):
    response = wms.create_product(builders.product(product))

    assert response.status_code == 409


@pytest.mark.negative
@pytest.mark.parametrize("field, value", [
    ("productId", ""),        # empty id
    ("productId", "X" * 21),  # one character over the 20 limit
    ("description", ""),      # empty description
    ("owner", ""),            # empty owner
])
def test_invalid_product_fields_are_rejected(wms, field, value):
    body = builders.product()
    body[field] = value

    response = wms.create_product(body)

    assert response.status_code == 422


def test_product_id_at_max_length_is_accepted(wms):
    response = wms.create_product(builders.product("X" * 20))

    assert response.status_code == 201
