from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tracegraph.models.base import Base
from tracegraph.models.enums import tier_enum


class Answer(Base):
    """
    #Feature: Reasoning audit
    #Scenario: Stored engine answer addressable by handle; every report claim binds to one
    #Complexity: Time O(1) - constant
    """

    __tablename__ = "answer"
    __table_args__ = (
        Index("ix_answer_handle", "handle", unique=True),
        Index("ix_answer_repo_id_snapshot_seq", "repo_id", "snapshot_seq"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    handle: Mapped[str] = mapped_column(Text, nullable=False)
    repo_id: Mapped[int] = mapped_column(Integer, ForeignKey("repo.id", ondelete="CASCADE"), nullable=False)
    snapshot_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    overlay_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("overlay.id", ondelete="SET NULL"))
    query_hash: Mapped[str] = mapped_column(Text, nullable=False)
    query_ir: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    truth: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    derivation: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
    min_tier: Mapped[str] = mapped_column(tier_enum, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
