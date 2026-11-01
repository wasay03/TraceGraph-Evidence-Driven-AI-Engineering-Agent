from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tracegraph.models.base import Base
from tracegraph.models.enums import snapshot_status_enum


class Snapshot(Base):
    """
    #Feature: Snapshots
    #Scenario: One indexed commit of a repo; seq is the version number stamped on graph rows
    #Complexity: Time O(1) - constant
    """

    __tablename__ = "snapshot"
    __table_args__ = (
        UniqueConstraint("repo_id", "seq"),
        Index("ix_snapshot_repo_id_status_seq", "repo_id", "status", "seq"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_id: Mapped[int] = mapped_column(Integer, ForeignKey("repo.id", ondelete="CASCADE"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    commit_sha: Mapped[str] = mapped_column(Text, nullable=False)
    ontology_version_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("ontology_version.id"))
    status: Mapped[str] = mapped_column(snapshot_status_enum, nullable=False, server_default="pending")
    extractor_versions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
