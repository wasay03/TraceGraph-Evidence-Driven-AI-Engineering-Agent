from datetime import datetime

from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from tracegraph.models.base import Base


class Repo(Base):
    """
    #Feature: Repositories
    #Scenario: A registered source repository; repo_id scopes every graph row (D15)
    #Complexity: Time O(1) - constant
    """

    __tablename__ = "repo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    default_branch: Mapped[str] = mapped_column(Text, nullable=False, server_default="main")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
