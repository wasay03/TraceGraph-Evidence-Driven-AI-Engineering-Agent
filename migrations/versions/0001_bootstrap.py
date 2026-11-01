"""bootstrap: health check function

Revision ID: 0001
Revises:
Create Date: 2026-11-01
"""
from collections.abc import Sequence

from alembic import op

from tracegraph.utilities import apply_sql_functions, drop_sql_functions

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SQL_FUNCTIONS: list[str] = ["system/tg_health_check.sql"]


def upgrade() -> None:
    apply_sql_functions(op, SQL_FUNCTIONS)


def downgrade() -> None:
    drop_sql_functions(op, SQL_FUNCTIONS)
