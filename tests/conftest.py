import os
from collections.abc import AsyncIterator

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient

from tracegraph.config import Settings

TEST_DATABASE_URL = os.environ.get("TG_TEST_DATABASE_URL", "postgresql+psycopg://tg@localhost:55432/tracegraph_test")
TEST_API_KEY = "test-key"


def _alembic_config() -> Config:
    config = Config("alembic.ini")
    config.cmd_opts = type("Opts", (), {"x": [f"url={TEST_DATABASE_URL}"]})()
    return config


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings(database_url=TEST_DATABASE_URL, api_key=TEST_API_KEY, log_level="WARNING")


@pytest.fixture(scope="session")
def migrated_db() -> str:
    config = _alembic_config()
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    return TEST_DATABASE_URL


@pytest.fixture(scope="session")
async def client(settings: Settings, migrated_db: str) -> AsyncIterator[AsyncClient]:
    from tracegraph.main import create_app

    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as http:
            yield http


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"X-API-Key": TEST_API_KEY}
