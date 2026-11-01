from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import INT4RANGE, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tracegraph.models.base import Base


class CoverageHole(Base):
    """
    #Feature: Coverage map
    #Scenario: Region where an extractor could not reach completeness (dynamic call, getattr, dynamic SQL...)
    #Complexity: Time O(1) - constant

    Read by three-valued negation to return UNKNOWN instead of FALSE.
    """

    __tablename__ = "coverage_hole"
    __table_args__ = (
        Index("ix_coverage_hole_repo_id_snapshot_seq_node_id", "repo_id", "snapshot_seq", "node_id"),
        Index("ix_coverage_hole_repo_id_snapshot_seq_file_path", "repo_id", "snapshot_seq", "file_path"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    repo_id: Mapped[int] = mapped_column(Integer, ForeignKey("repo.id", ondelete="CASCADE"), nullable=False)
    snapshot_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    node_id: Mapped[int | None] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str | None] = mapped_column(Text)
    span: Mapped[Any | None] = mapped_column(INT4RANGE)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
