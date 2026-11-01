from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    #Feature: Configuration
    #Scenario: Load runtime settings from environment variables prefixed with TG_
    #Complexity: Time O(1) - constant

    Typed application settings.
    """

    model_config = SettingsConfigDict(env_prefix="TG_", env_file=".env", extra="ignore")

    database_url: str = Field(default="postgresql+psycopg://tg:tg@localhost:5432/tracegraph")
    api_key: str = Field(default="change-me", min_length=1)
    log_level: str = Field(default="INFO")
    workspace_dir: str = Field(default="/tmp/tracegraph/worktrees")
    db_pool_size: int = Field(default=10, ge=1)
    worker_poll_seconds: float = Field(default=1.0, gt=0)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    #Feature: Configuration
    #Scenario: Provide a process-wide cached Settings instance
    #Complexity: Time O(1) - constant after first call

    Returns the cached settings object.

    Returns:
        Settings loaded from the environment.

    Raises:
        RuntimeError: When the environment holds invalid settings.
    """
    try:
        return Settings()
    except Exception as exc:
        raise RuntimeError(
            f"[get_settings] Failed to load settings. "
            f"Invariant violated: TG_* environment variables must be valid. "
            f"Received: {exc}. Fix: correct the environment or .env file."
        ) from exc
