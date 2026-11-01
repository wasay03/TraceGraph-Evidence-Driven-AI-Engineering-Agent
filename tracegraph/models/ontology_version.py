from datetime import datetime

from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from tracegraph.models.base import Base


class OntologyVersion(Base):
    """
    #Feature: Ontology catalog
    #Scenario: One row per registry version loaded into the catalog
    #Complexity: Time O(1) - constant
    """

    __tablename__ = "ontology_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    semver: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
