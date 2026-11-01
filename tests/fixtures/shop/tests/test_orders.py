import pytest

from app.models import Order
from app.services import calculate_total, get_discount


def test_calculate_total_applies_discount(order: Order) -> None:
    assert calculate_total(order) == 90


@pytest.mark.parametrize("code", ["WELCOME", "VIP"])
def test_known_discounts(code: str) -> None:
    assert get_discount(code) is not None
