"""tg_run_list for the runs page

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-01
"""
from collections.abc import Sequence

from alembic import op

from tracegraph.utilities import apply_sql_functions, drop_sql_functions

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SQL_FUNCTIONS: list[str] = ["run/tg_run_list.sql"]


def upgrade() -> None:
    apply_sql_functions(op, SQL_FUNCTIONS)


def downgrade() -> None:
    drop_sql_functions(op, SQL_FUNCTIONS)
