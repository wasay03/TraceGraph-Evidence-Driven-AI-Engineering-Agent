from typing import Protocol

from tracegraph.utilities.sql_files import function_name_of, read_sql_file


class _MigrationOps(Protocol):
    """
    #Feature: Migrations
    #Scenario: The subset of alembic.op used here, so callers inject it
    #Complexity: Time O(1) - constant
    """

    def execute(self, sqltext: str) -> None: ...


def apply_sql_functions(op: _MigrationOps, relative_paths: list[str]) -> None:
    """
    #Feature: Migrations
    #Scenario: Install or replace stored functions, one file per function, in the given order
    #Complexity: Time O(f) - linear in number of files

    Function bodies are not validated at create time so a file may reference tables
    created later in the same migration chain.

    Args:
        op: Alembic operations object.
        relative_paths: Paths relative to sql/functions.

    Raises:
        ValueError: When op is None or a file is missing.
    """
    if op is None:
        raise ValueError("[apply_sql_functions] 'op' is required and must not be None.")
    op.execute("SET LOCAL check_function_bodies = off")
    for path in relative_paths:
        op.execute(read_sql_file(path))


def drop_sql_functions(op: _MigrationOps, relative_paths: list[str]) -> None:
    """
    #Feature: Migrations
    #Scenario: Drop stored functions in reverse order on downgrade
    #Complexity: Time O(f) - linear in number of files

    Args:
        op: Alembic operations object.
        relative_paths: Paths relative to sql/functions, as passed to apply_sql_functions.

    Raises:
        ValueError: When op is None.
    """
    if op is None:
        raise ValueError("[drop_sql_functions] 'op' is required and must not be None.")
    for path in reversed(relative_paths):
        op.execute(f"DROP FUNCTION IF EXISTS {function_name_of(path)}")
