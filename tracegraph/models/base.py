from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """
    #Feature: Persistence schema
    #Scenario: Declarative base for table definitions used only by Alembic migrations
    #Complexity: Time O(1) - constant

    Application code never queries through these models; repositories call stored functions.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
