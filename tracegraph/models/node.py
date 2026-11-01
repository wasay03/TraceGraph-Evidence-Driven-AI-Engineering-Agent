from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, SmallInteger, Text, text
from sqlalchemy.dialects.postgresql import INT4RANGE, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tracegraph.models.base import Base
from tracegraph.models.enums import tier_enum


class Node(Base):
    """
    #Feature: Graph store
    #Scenario: Versioned typed node; valid_from/valid_to are snapshot seqs, valid_to NULL means current
    #Complexity: Time O(1) - constant
    """

    __tablename__ = "node"
    __table_args__ = (
        Index(
            "ix_node_current_key",
            "repo_id",
            "type_id",
            "natural_key",
            unique=True,
            postgresql_where=text("valid_to IS NULL"),
        ),
        Index("ix_node_current_file", "repo_id", "file_path", postgresql_where=text("valid_to IS NULL")),
        Index("ix_node_props", "props", postgresql_using="gin", postgresql_ops={"props": "jsonb_path_ops"}),
        Index(
            "ix_node_natural_key_trgm",
            "natural_key",
            postgresql_using="gin",
            postgresql_ops={"natural_key": "gin_trgm_ops"},
        ),
    )

    repo_id: Mapped[int] = mapped_column(Integer, ForeignKey("repo.id", ondelete="CASCADE"), primary_key=True)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    valid_from: Mapped[int] = mapped_column(Integer, primary_key=True)
    valid_to: Mapped[int | None] = mapped_column(Integer)
    type_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("node_type.id"), nullable=False)
    natural_key: Mapped[str] = mapped_column(Text, nullable=False)
    props: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    tier: Mapped[str] = mapped_column(tier_enum, nullable=False)
    file_path: Mapped[str | None] = mapped_column(Text)
    span: Mapped[Any | None] = mapped_column(INT4RANGE)
