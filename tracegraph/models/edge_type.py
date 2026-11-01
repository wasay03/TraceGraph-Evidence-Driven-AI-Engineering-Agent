from typing import Any

from sqlalchemy import SmallInteger, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tracegraph.models.base import Base


class EdgeType(Base):
    """
    #Feature: Ontology catalog
    #Scenario: Registered edge type with cardinality, inverse, algebraic flags, tiers and evidence policy
    #Complexity: Time O(1) - constant
    """

    __tablename__ = "edge_type"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    cardinality: Mapped[str] = mapped_column(Text, nullable=False)
    inverse_name: Mapped[str | None] = mapped_column(Text)
    flags: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    tiers: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    evidence_policy: Mapped[str] = mapped_column(Text, nullable=False, server_default="span_required")
