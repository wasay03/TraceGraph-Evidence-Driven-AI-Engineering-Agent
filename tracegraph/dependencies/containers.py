from collections.abc import AsyncIterator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from tracegraph.config import Settings, get_settings
from tracegraph.containers import RepositoryContainer, ServiceContainer


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """
    #Feature: Dependency injection
    #Scenario: One transactional session per request, owned by app.state.database
    #Complexity: Time O(1) - constant

    Args:
        request: Incoming request.

    Yields:
        AsyncSession committed after the handler returns.

    Raises:
        RuntimeError: When the application was started without a Database.
    """
    database = getattr(request.app.state, "database", None)
    if database is None:
        raise RuntimeError("[get_db_session] app.state.database is not set. Fix: start the app via create_app().")
    async for session in database.session():
        yield session


def get_repository_container(session: AsyncSession = Depends(get_db_session)) -> RepositoryContainer:
    """
    #Feature: Dependency injection
    #Scenario: Build the per-request repository container
    #Complexity: Time O(1) - constant

    Args:
        session: Request session.

    Returns:
        RepositoryContainer.
    """
    return RepositoryContainer(session)


def get_service_container(
    repositories: RepositoryContainer = Depends(get_repository_container),
    settings: Settings = Depends(get_settings),
) -> ServiceContainer:
    """
    #Feature: Dependency injection
    #Scenario: Build the per-request service container
    #Complexity: Time O(1) - constant

    Args:
        repositories: Per-request repository container.
        settings: Application settings.

    Returns:
        ServiceContainer.
    """
    return ServiceContainer(repositories=repositories, settings=settings)
