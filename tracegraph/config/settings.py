from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
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
    sandbox_dir: str = Field(default="/tmp/tracegraph/sandboxes")
    sandbox_python: str | None = Field(default=None, description="Interpreter used to run the target repo's tests")
    llm_provider: Literal["anthropic", "gemini"] = Field(default="anthropic")
    llm_model: str | None = Field(default=None, description="Model id; required for gemini, anthropic has a default")
    llm_api_key: SecretStr | None = Field(
        default=None, description="Falls back to the provider SDK's own variables (GEMINI_API_KEY / ANTHROPIC_API_KEY)"
    )
    llm_api_key_fallback_1: SecretStr | None = Field(default=None, description="Tried when the main key fails")
    llm_api_key_fallback_2: SecretStr | None = Field(default=None, description="Tried when fallback 1 also fails")
    llm_max_output_tokens: int = Field(default=16000, ge=256)
    llm_min_seconds_between_calls: float = Field(default=5.0, ge=0, description="Pacing for rate-limited API tiers")
    llm_max_calls_per_run: int = Field(default=40, ge=1, description="Hard cap on model requests in one agent run")


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
