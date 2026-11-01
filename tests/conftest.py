import os
import shutil
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient

from tracegraph.config import Settings

TEST_DATABASE_URL = os.environ.get("TG_TEST_DATABASE_URL", "postgresql+psycopg://tg@localhost:55432/tracegraph_test")
TEST_API_KEY = "test-key"
SHOP_FIXTURE = Path(__file__).parent / "fixtures" / "shop"


def git(path: Path, *args: str) -> str:
    cmd = ["git", "-C", str(path), "-c", "user.email=t@t", "-c", "user.name=t", *args]
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.strip()


def commit_all(path: Path, message: str) -> str:
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", message)
    return git(path, "rev-parse", "HEAD")


@pytest.fixture
def shop_repo(tmp_path: Path) -> Path:
    path = tmp_path / "shop"
    shutil.copytree(SHOP_FIXTURE, path, ignore=shutil.ignore_patterns("__pycache__"))
    git(path, "init", "-q", "-b", "main")
    commit_all(path, "seed")
    return path


def _alembic_config() -> Config:
    config = Config("alembic.ini")
    config.cmd_opts = type("Opts", (), {"x": [f"url={TEST_DATABASE_URL}"]})()
    return config


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings(_env_file=None, database_url=TEST_DATABASE_URL, api_key=TEST_API_KEY, log_level="WARNING")


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
