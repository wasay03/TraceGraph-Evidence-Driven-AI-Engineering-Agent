from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tracegraph.models.base import Base


class Overlay(Base):
    """
    #Feature: What-if analysis
    #Scenario: Hypothesized change set evaluated on top of a base snapshot
    #Complexity: Time O(1) - constant
    """

    __tablename__ = "overlay"
    __table_args__ = (Index("ix_overlay_repo_id_base_seq", "repo_id", "base_seq"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    repo_id: Mapped[int] = mapped_column(Integer, ForeignKey("repo.id", ondelete="CASCADE"), nullable=False)
    base_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    change_spec: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
