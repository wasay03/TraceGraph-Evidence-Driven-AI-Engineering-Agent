import pytest

from app.models import Order


@pytest.fixture
def order() -> Order:
    return Order(tenant_id=1, total=100, discount_code="WELCOME")
