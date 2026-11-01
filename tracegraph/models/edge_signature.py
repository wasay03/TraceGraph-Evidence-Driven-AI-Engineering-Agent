from sqlalchemy import ForeignKey, Index, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from tracegraph.models.base import Base


class EdgeSignature(Base):
    """
    #Feature: Ontology catalog
    #Scenario: Permitted (domain, range) node-type pair for an edge type; subtypes inherit it
    #Complexity: Time O(1) - constant
    """

    __tablename__ = "edge_signature"
    __table_args__ = (Index("ix_edge_signature_domain_range", "domain_type_id", "range_type_id"),)

    edge_type_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("edge_type.id"), primary_key=True)
    domain_type_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("node_type.id"), primary_key=True)
    range_type_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("node_type.id"), primary_key=True)
