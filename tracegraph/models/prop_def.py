from sqlalchemy import Boolean, CheckConstraint, SmallInteger, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from tracegraph.models.base import Base


class PropDef(Base):
    """
    #Feature: Ontology catalog
    #Scenario: Typed property declared on a node or edge type
    #Complexity: Time O(1) - constant
    """

    __tablename__ = "prop_def"
    __table_args__ = (CheckConstraint("owner_kind IN ('node', 'edge')", name="owner_kind"),)

    owner_kind: Mapped[str] = mapped_column(Text, primary_key=True)
    owner_type_id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, primary_key=True)
    value_type: Mapped[str] = mapped_column(Text, nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    enum_values: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
