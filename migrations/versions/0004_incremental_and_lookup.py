"""incremental dirty-set and repository lookup functions

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-01
"""
from collections.abc import Sequence

from alembic import op

from tracegraph.utilities import apply_sql_functions, drop_sql_functions

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SQL_FUNCTIONS: list[str] = ["graph/tg_node_list_by_type_at.sql", "repo/tg_repo_find_by_url.sql"]


def upgrade() -> None:
    apply_sql_functions(op, SQL_FUNCTIONS)


def downgrade() -> None:
    drop_sql_functions(op, SQL_FUNCTIONS)
