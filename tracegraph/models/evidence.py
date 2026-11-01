from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import INT4RANGE, REAL
from sqlalchemy.orm import Mapped, mapped_column

from tracegraph.models.base import Base


class Evidence(Base):
    """
    #Feature: Provenance
    #Scenario: Source justification for an edge: extractor, method, file and line span
    #Complexity: Time O(1) - constant

    id is a content hash, so identical evidence across snapshots is stored once.
    """

    __tablename__ = "evidence"
    __table_args__ = (Index("ix_evidence_repo_id_file_path", "repo_id", "file_path"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    repo_id: Mapped[int] = mapped_column(Integer, ForeignKey("repo.id", ondelete="CASCADE"), nullable=False)
    extractor: Mapped[str] = mapped_column(Text, nullable=False)
    extractor_version: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str | None] = mapped_column(Text)
    span: Mapped[Any | None] = mapped_column(INT4RANGE)
    snippet_hash: Mapped[str | None] = mapped_column(Text)
    commit_sha: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(REAL)
    rationale: Mapped[str | None] = mapped_column(Text)
