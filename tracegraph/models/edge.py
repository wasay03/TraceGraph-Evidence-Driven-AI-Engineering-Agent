from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, SmallInteger, Text, text
from sqlalchemy.dialects.postgresql import JSONB, REAL
from sqlalchemy.orm import Mapped, mapped_column

from tracegraph.models.base import Base
from tracegraph.models.enums import tier_enum


class Edge(Base):
    """
    #Feature: Graph store
    #Scenario: Versioned typed edge; owner_file is the file of its domain-side evidence (incremental unit)
    #Complexity: Time O(1) - constant
    """

    __tablename__ = "edge"
    __table_args__ = (
        Index(
            "ix_edge_current_fwd",
            "repo_id",
            "type_id",
            "src",
            postgresql_include=["dst", "tier"],
            postgresql_where=text("valid_to IS NULL"),
        ),
        Index(
            "ix_edge_current_rev",
            "repo_id",
            "type_id",
            "dst",
            postgresql_include=["src", "tier"],
            postgresql_where=text("valid_to IS NULL"),
        ),
        Index("ix_edge_current_owner_file", "repo_id", "owner_file", postgresql_where=text("valid_to IS NULL")),
    )

    repo_id: Mapped[int] = mapped_column(Integer, ForeignKey("repo.id", ondelete="CASCADE"), primary_key=True)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    valid_from: Mapped[int] = mapped_column(Integer, primary_key=True)
    valid_to: Mapped[int | None] = mapped_column(Integer)
    type_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("edge_type.id"), nullable=False)
    src: Mapped[int] = mapped_column(BigInteger, nullable=False)
    dst: Mapped[int] = mapped_column(BigInteger, nullable=False)
    props: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    tier: Mapped[str] = mapped_column(tier_enum, nullable=False)
    confidence: Mapped[float | None] = mapped_column(REAL)
    owner_file: Mapped[str | None] = mapped_column(Text)
