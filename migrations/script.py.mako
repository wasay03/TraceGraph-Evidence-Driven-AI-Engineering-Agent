"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
${imports if imports else ""}
from tracegraph.utilities import apply_sql_functions, drop_sql_functions

revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}

# Stored functions installed by this revision, relative to sql/functions.
SQL_FUNCTIONS: list[str] = []


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}
    apply_sql_functions(op, SQL_FUNCTIONS)


def downgrade() -> None:
    drop_sql_functions(op, SQL_FUNCTIONS)
    ${downgrades if downgrades else "pass"}
