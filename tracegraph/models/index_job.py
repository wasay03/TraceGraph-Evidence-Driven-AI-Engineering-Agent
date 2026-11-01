from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tracegraph.models.base import Base
from tracegraph.models.enums import job_kind_enum, job_status_enum


class IndexJob(Base):
    """
    #Feature: Background indexing
    #Scenario: Queue row claimed by workers with SELECT ... FOR UPDATE SKIP LOCKED
    #Complexity: Time O(1) - constant
    """

    __tablename__ = "index_job"
    __table_args__ = (
        Index("ix_index_job_queued", "created_at", postgresql_where=text("status = 'queued'")),
        Index("ix_index_job_snapshot_id", "snapshot_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    repo_id: Mapped[int] = mapped_column(Integer, ForeignKey("repo.id", ondelete="CASCADE"), nullable=False)
    snapshot_id: Mapped[int] = mapped_column(Integer, ForeignKey("snapshot.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(job_kind_enum, nullable=False)
    status: Mapped[str] = mapped_column(job_status_enum, nullable=False, server_default="queued")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    locked_by: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
