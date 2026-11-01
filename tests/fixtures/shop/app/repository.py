from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Order, OrderStatus


class Repository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, obj: object) -> None:
        self.session.add(obj)


class OrderRepository(Repository):
    def save(self, obj: Order) -> None:
        self.session.add(obj)
        self.session.flush()

    def get(self, order_id: int) -> Order | None:
        return self.session.get(Order, order_id)

    def list_paid(self, tenant_id: int) -> list[Order]:
        stmt = select(Order).where(Order.tenant_id == tenant_id, Order.status == OrderStatus.PAID)
        return list(self.session.scalars(stmt))

    def mark_refunded(self, order_id: int) -> None:
        self.session.execute(update(Order).where(Order.id == order_id).values(status=OrderStatus.REFUNDED))
