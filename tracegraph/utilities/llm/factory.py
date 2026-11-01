import logging

from tracegraph.config import Settings
from tracegraph.constants.llm import ANTHROPIC_DEFAULT_MODEL, PROVIDER_ANTHROPIC, PROVIDER_GEMINI
from tracegraph.interfaces.llm import ILlmClient
from tracegraph.utilities.llm.fallback import FallbackLlmClient
from tracegraph.utilities.llm.throttle import ThrottledLlmClient

logger = logging.getLogger(__name__)


def _api_keys(settings: Settings) -> list[str | None]:
    """
    #Feature: LLM utility
    #Scenario: Configured keys in priority order, blanks and duplicates dropped; [None] lets the provider SDK read
               its own variable when no TG_LLM_API_KEY* is set
    #Complexity: Time O(1) - three settings
    """
    values = (settings.llm_api_key, settings.llm_api_key_fallback_1, settings.llm_api_key_fallback_2)
    keys = list(dict.fromkeys(v.get_secret_value() for v in values if v and v.get_secret_value()))
    return keys or [None]


def _provider_client(settings: Settings, api_key: str | None) -> ILlmClient:
    """
    #Feature: LLM utility
    #Scenario: One adapter for one key; provider SDKs are imported only for the selected provider
    #Complexity: Time O(1) - constant

    Raises:
        ValueError: When the provider is unknown or gemini has no model.
    """
    if settings.llm_provider == PROVIDER_GEMINI:
        from tracegraph.utilities.llm.gemini_client import GeminiLlmClient

        if not settings.llm_model:
            raise ValueError("[create_llm_client] TG_LLM_MODEL is required when TG_LLM_PROVIDER=gemini "
                             "(e.g. TG_LLM_MODEL=gemini-3.5-flash-lite).")
        return GeminiLlmClient(settings.llm_model, settings.llm_max_output_tokens, api_key)
    if settings.llm_provider == PROVIDER_ANTHROPIC:
        from tracegraph.utilities.llm.anthropic_client import AnthropicLlmClient

        return AnthropicLlmClient(settings.llm_model or ANTHROPIC_DEFAULT_MODEL, settings.llm_max_output_tokens, api_key)
    raise ValueError(f"[create_llm_client] Unknown TG_LLM_PROVIDER {settings.llm_provider!r}. "
                     f"Fix: use {PROVIDER_ANTHROPIC} or {PROVIDER_GEMINI}.")


def create_llm_client(settings: Settings) -> ILlmClient:
    """
    #Feature: LLM utility
    #Scenario: Build the agent's LLM client from TG_LLM_PROVIDER, TG_LLM_MODEL and TG_LLM_API_KEY plus optional
               TG_LLM_API_KEY_FALLBACK_1/2; several keys are wrapped so a failing key falls over to the next
    #Complexity: Time O(k) - configured keys

    Args:
        settings: Application settings.

    Returns:
        An ILlmClient for the configured provider.

    Raises:
        ValueError: When settings is None, the provider is unknown, or gemini has no model.
    """
    if settings is None:
        raise ValueError("[create_llm_client] 'settings' is required.")
    clients = [_provider_client(settings, key) for key in _api_keys(settings)]
    logger.info("LLM client created", extra={"provider": settings.llm_provider, "model": settings.llm_model,
                                             "keys": len(clients)})
    client = clients[0] if len(clients) == 1 else FallbackLlmClient(clients)
    return ThrottledLlmClient(client, settings.llm_min_seconds_between_calls)
