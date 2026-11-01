from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from tracegraph.config import Settings


class Database:
    """
    #Feature: Persistence
    #Scenario: Own the async engine and session factory for the process lifetime
    #Complexity: Time O(1) - constant

    Composition-root object; created once at startup and disposed at shutdown.
    """

    def __init__(self, settings: Settings) -> None:
        """
        #Feature: Persistence
        #Scenario: Build the engine from settings
        #Complexity: Time O(1) - constant

        Args:
            settings: Application settings holding the database URL.

        Raises:
            ValueError: When settings is None.
        """
        if settings is None:
            raise ValueError("[Database.__init__] 'settings' is required and must not be None.")
        self._engine: AsyncEngine = create_async_engine(
            settings.database_url, pool_size=settings.db_pool_size, pool_pre_ping=True
        )
        self._sessions = async_sessionmaker(self._engine, expire_on_commit=False)

    async def session(self) -> AsyncIterator[AsyncSession]:
        """
        #Feature: Persistence
        #Scenario: Provide one transactional session; commit on success, roll back on error
        #Complexity: Time O(1) - constant

        Yields:
            An AsyncSession bound to a transaction.
        """
        async with self._sessions() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def dispose(self) -> None:
        """
        #Feature: Persistence
        #Scenario: Close the connection pool at shutdown
        #Complexity: Time O(n) - linear in pooled connections
        """
        try:
            await self._engine.dispose()
        except Exception as exc:
            raise RuntimeError(f"[Database.dispose] Failed to dispose engine: {exc}.") from exc
