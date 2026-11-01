from sqlalchemy import text
from sqlalchemy.orm import Session


def paid_order_ids(session: Session) -> list[int]:
    rows = session.execute(text("SELECT id FROM orders WHERE status = 'paid'"))
    return [row[0] for row in rows]


def count_rows(session: Session, table: str) -> int:
    return session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()


def run_hook(name: str) -> object:
    import app.services as services

    return getattr(services, name)()
