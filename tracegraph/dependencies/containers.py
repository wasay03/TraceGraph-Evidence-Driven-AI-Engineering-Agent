from collections.abc import AsyncIterator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from tracegraph.config import Settings
from tracegraph.containers import RepositoryContainer, ServiceContainer


def get_app_settings(request: Request) -> Settings:
    """
    #Feature: Dependency injection
    #Scenario: Settings the application was created with (composition root), not re-read from the environment
    #Complexity: Time O(1) - constant

    Raises:
        RuntimeError: When the application was not built by create_app().
    """
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        raise RuntimeError("[get_app_settings] app.state.settings is not set. Fix: start the app via create_app().")
    return settings


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
    request: Request,
    repositories: RepositoryContainer = Depends(get_repository_container),
    settings: Settings = Depends(get_app_settings),
) -> ServiceContainer:
    """
    #Feature: Dependency injection
    #Scenario: Build the per-request service container
    #Complexity: Time O(1) - constant

    Args:
        request: Incoming request (for the app-scoped snapshot cache).
        repositories: Per-request repository container.
        settings: Application settings.

    Returns:
        ServiceContainer.
    """
    return ServiceContainer(repositories=repositories, settings=settings,
                            snapshot_cache=getattr(request.app.state, "snapshot_cache", None))
