from sqlalchemy import Boolean, ForeignKey, Index, SmallInteger, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from tracegraph.models.base import Base


class NodeType(Base):
    """
    #Feature: Ontology catalog
    #Scenario: Registered node type with single-inheritance parent, key fields and allowed tiers
    #Complexity: Time O(1) - constant
    """

    __tablename__ = "node_type"
    __table_args__ = (Index("ix_node_type_parent_id", "parent_id"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    parent_id: Mapped[int | None] = mapped_column(SmallInteger, ForeignKey("node_type.id"))
    is_abstract: Mapped[bool] = mapped_column(Boolean, nullable=False)
    natural_key: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    tiers: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    owner: Mapped[str | None] = mapped_column(Text)
