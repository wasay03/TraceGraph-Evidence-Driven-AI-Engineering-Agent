from app.models import Invoice, Order, OrderStatus
from app.repository import OrderRepository
from app.schemas import OrderIn

DISCOUNTS = {"WELCOME": 10, "VIP": 25}


class RefundError(Exception):
    pass


def get_discount(code: str) -> int | None:
    return DISCOUNTS.get(code)


def calculate_total(order: Order) -> int:
    percent = get_discount(order.discount_code.upper())
    if percent is None:
        return order.total
    return order.total - order.total * percent // 100


def describe_status(order: Order) -> str:
    if order.status == OrderStatus.PENDING:
        return "waiting for payment"
    elif order.status == OrderStatus.PAID:
        return "paid"
    return "unknown"


class OrderService:
    def __init__(self, repository: OrderRepository) -> None:
        self.repository = repository

    def create_order(self, data: OrderIn) -> Order:
        order = Order(tenant_id=data.tenant_id, total=data.total, discount_code=data.discount_code)
        order.total = calculate_total(order)
        self.repository.save(order)
        return order

    def refund(self, order_id: int) -> Invoice:
        order = self.repository.get(order_id)
        if order is None or order.status != OrderStatus.PAID:
            raise RefundError("only paid orders can be refunded")
        self.repository.mark_refunded(order_id)
        return Invoice(order_id=order_id, amount=-order.total)
