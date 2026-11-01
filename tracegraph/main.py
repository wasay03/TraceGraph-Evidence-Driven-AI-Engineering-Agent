from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from tracegraph.config import Settings, get_settings
from tracegraph.core import Database, configure_logging
from tracegraph.engine import SnapshotCache
from tracegraph.errors import register_error_handlers
from tracegraph.middleware import RequestContextMiddleware
from tracegraph.routers import ALL_ROUTERS
from tracegraph.services.agent_executor import AgentExecutor
from tracegraph.utilities.llm import create_llm_client


def _lifespan(settings: Settings):
    """
    #Feature: Application lifecycle
    #Scenario: Create the Database at startup and dispose it at shutdown
    #Complexity: Time O(1) - constant

    Args:
        settings: Application settings.

    Returns:
        Lifespan context manager factory for FastAPI.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.database = Database(settings)
        app.state.agent_executor = AgentExecutor(app.state.database, settings, app.state.snapshot_cache,
                                                 lambda: create_llm_client(settings))
        try:
            yield
        finally:
            await app.state.database.dispose()

    return lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    """
    #Feature: Application lifecycle
    #Scenario: Composition root; wires logging, middleware, error handlers and routers
    #Complexity: Time O(r) - linear in number of routers

    Args:
        settings: Optional settings override, used by tests.

    Returns:
        Configured FastAPI application.
    """
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(title="TraceGraph", version="0.1.0", lifespan=_lifespan(settings))
    app.state.settings = settings
    app.state.snapshot_cache = SnapshotCache()
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)
    for router in ALL_ROUTERS:
        app.include_router(router)
    return app
