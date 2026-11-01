import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tracegraph.core.tracing import sql_function, tracer
from tracegraph.errors import AppError, Errors

logger = logging.getLogger(__name__)

# Custom SQLSTATEs raised by stored functions (RAISE ... USING ERRCODE = 'TG404').
_SQLSTATE_ERRORS: dict[str, type[AppError]] = {
    "TG400": Errors.HTTP.BadRequest,
    "TG404": Errors.HTTP.NotFound,
    "TG409": Errors.HTTP.Conflict,
    "TG422": Errors.Domain.Base,
}


def _translate_db_error(exc: DBAPIError, statement: str) -> AppError:
    """
    #Feature: Persistence
    #Scenario: Map a driver error raised by a stored function to the error taxonomy
    #Complexity: Time O(1) - constant

    Args:
        exc: SQLAlchemy DBAPI error.
        statement: The SQL that failed, used for context.

    Returns:
        A typed AppError.
    """
    sqlstate = getattr(exc.orig, "sqlstate", None)
    message = str(getattr(exc.orig, "diag", None) and exc.orig.diag.message_primary or exc.orig)
    details = {"sqlstate": sqlstate, "statement": statement.split("(")[0]}
    if sqlstate in _SQLSTATE_ERRORS:
        return _SQLSTATE_ERRORS[sqlstate](message, details)
    if isinstance(exc, IntegrityError):
        return Errors.Database.IntegrityError(message, details)
    return Errors.Database.QueryError(f"[UdfRepository] Stored function call failed: {message}", details)


class UdfRepository:
    """
    #Feature: Persistence
    #Scenario: Base for repositories; every read and write goes through a stored function
    #Complexity: Time O(1) - constant per call excluding the database work

    Subclasses define SELECT * FROM tg_<fn>(...) statements with bound parameters only.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        #Feature: Persistence
        #Scenario: Bind the repository to the request or job session
        #Complexity: Time O(1) - constant

        Args:
            session: Active AsyncSession.

        Raises:
            ValueError: When session is None.
        """
        if session is None:
            raise ValueError(f"[{type(self).__name__}.__init__] 'session' is required and must not be None.")
        self._session = session

    async def _execute(self, statement: str, params: dict[str, Any] | None = None) -> Any:
        """
        #Feature: Persistence
        #Scenario: Run one stored-function statement and translate driver errors
        #Complexity: Time O(1) - constant excluding database work

        Args:
            statement: SQL calling a single stored function.
            params: Bound parameters.

        Returns:
            SQLAlchemy result.

        Raises:
            AppError: Typed error mapped from the database failure.
        """
        try:
            with tracer().start_as_current_span(f"sql {sql_function(statement)}"):
                return await self._session.execute(text(statement), params or {})
        except DBAPIError as exc:
            error = _translate_db_error(exc, statement)
            logger.warning(error.message, extra={"code": error.code, **error.details})
            raise error from exc

    async def _fetch_all(self, statement: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """
        #Feature: Persistence
        #Scenario: Fetch every row returned by a set-returning function
        #Complexity: Time O(r) - linear in rows

        Args:
            statement: SQL calling a single stored function.
            params: Bound parameters.

        Returns:
            Rows as dictionaries.
        """
        result = await self._execute(statement, params)
        return [dict(row) for row in result.mappings().all()]

    async def _fetch_one(self, statement: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """
        #Feature: Persistence
        #Scenario: Fetch at most one row returned by a function
        #Complexity: Time O(1) - constant

        Args:
            statement: SQL calling a single stored function.
            params: Bound parameters.

        Returns:
            Row as a dictionary, or None when no row was returned.
        """
        result = await self._execute(statement, params)
        row = result.mappings().first()
        return dict(row) if row is not None else None

    async def _fetch_scalar(self, statement: str, params: dict[str, Any] | None = None) -> Any:
        """
        #Feature: Persistence
        #Scenario: Fetch the single value returned by a scalar function
        #Complexity: Time O(1) - constant

        Args:
            statement: SQL calling a single stored function.
            params: Bound parameters.

        Returns:
            The scalar value.
        """
        result = await self._execute(statement, params)
        return result.scalar()
