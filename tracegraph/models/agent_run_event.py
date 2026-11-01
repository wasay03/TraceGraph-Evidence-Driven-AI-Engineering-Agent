from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tracegraph.models.base import Base


class AgentRunEvent(Base):
    """
    #Feature: Agent audit log (PRD 9.3)
    #Scenario: Append-only log of tool calls, LLM turns, phase transitions and approvals of a run
    #Complexity: Time O(1) - constant
    """

    __tablename__ = "agent_run_event"
    __table_args__ = (
        CheckConstraint("kind IN ('tool_call', 'llm_turn', 'transition', 'approval', 'error')", name="kind"),
        Index("ix_agent_run_event_run_id_seq", "run_id", "seq", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("agent_run.id", ondelete="CASCADE"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    phase: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
