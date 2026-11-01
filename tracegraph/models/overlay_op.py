from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tracegraph.models.base import Base
from tracegraph.models.enums import overlay_op_enum


class OverlayOp(Base):
    """
    #Feature: What-if analysis
    #Scenario: One ordered graph operation inside an overlay
    #Complexity: Time O(1) - constant
    """

    __tablename__ = "overlay_op"
    __table_args__ = (Index("ix_overlay_op_overlay_id_position", "overlay_id", "position", unique=True),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    overlay_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("overlay.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    op: Mapped[str] = mapped_column(overlay_op_enum, nullable=False)
    target_id: Mapped[int | None] = mapped_column(BigInteger)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
