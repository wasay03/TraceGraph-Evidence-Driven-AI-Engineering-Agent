from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.repository import OrderRepository
from app.schemas import OrderIn, OrderOut
from app.services import OrderService, RefundError, describe_status

router = APIRouter(prefix="/orders")


def get_order_service(session: Session = Depends(get_session)) -> OrderService:
    return OrderService(OrderRepository(session))


@router.post("", response_model=OrderOut, status_code=201)
def create_order(payload: OrderIn, service: OrderService = Depends(get_order_service)) -> OrderOut:
    order = service.create_order(payload)
    return OrderOut(id=order.id, status=describe_status(order), total=order.total)


@router.post("/{order_id}/refund", status_code=200)
def refund_order(order_id: int, service: OrderService = Depends(get_order_service)) -> dict:
    try:
        invoice = service.refund(order_id)
    except RefundError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"amount": invoice.amount}
