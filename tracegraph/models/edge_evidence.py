from sqlalchemy import BigInteger, ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column

from tracegraph.models.base import Base


class EdgeEvidence(Base):
    """
    #Feature: Provenance
    #Scenario: Link from a (stable) edge id to the evidence that currently justifies it
    #Complexity: Time O(1) - constant
    """

    __tablename__ = "edge_evidence"
    __table_args__ = (Index("ix_edge_evidence_evidence_id", "evidence_id"),)

    repo_id: Mapped[int] = mapped_column(Integer, ForeignKey("repo.id", ondelete="CASCADE"), primary_key=True)
    edge_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    evidence_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("evidence.id", ondelete="CASCADE"), primary_key=True)
