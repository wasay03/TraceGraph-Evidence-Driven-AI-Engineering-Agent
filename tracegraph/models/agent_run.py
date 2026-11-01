from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tracegraph.models.base import Base


class AgentRun(Base):
    """
    #Feature: Agent runs (PRD 10.5)
    #Scenario: One persisted agent run; state is versioned per transition (optimistic concurrency on version)
    #Complexity: Time O(1) - constant
    """

    __tablename__ = "agent_run"
    __table_args__ = (
        CheckConstraint("mode IN ('interactive', 'benchmark')", name="mode"),
        CheckConstraint(
            "status IN ('queued', 'running', 'awaiting_approval', 'awaiting_user', 'completed', 'failed', "
            "'budget_exhausted', 'rejected')",
            name="status",
        ),
        Index("ix_agent_run_repo_id_created_at", "repo_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    repo_id: Mapped[int] = mapped_column(Integer, ForeignKey("repo.id", ondelete="CASCADE"), nullable=False)
    snapshot_id: Mapped[int] = mapped_column(Integer, ForeignKey("snapshot.id", ondelete="CASCADE"), nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="queued")
    phase: Mapped[str] = mapped_column(Text, nullable=False, server_default="intake")
    request: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
