import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    op.add_column("orders", sa.Column("discount_code", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "discount_code")
