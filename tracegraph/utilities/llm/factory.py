import logging

from tracegraph.config import Settings
from tracegraph.constants.llm import ANTHROPIC_DEFAULT_MODEL, PROVIDER_ANTHROPIC, PROVIDER_GEMINI
from tracegraph.interfaces.llm import ILlmClient

logger = logging.getLogger(__name__)


def create_llm_client(settings: Settings) -> ILlmClient:
    """
    #Feature: LLM utility
    #Scenario: Build the agent's LLM client from TG_LLM_PROVIDER / TG_LLM_MODEL / TG_LLM_API_KEY; provider SDKs are
               imported only for the selected provider
    #Complexity: Time O(1) - constant

    Args:
        settings: Application settings.

    Returns:
        An ILlmClient for the configured provider.

    Raises:
        ValueError: When settings is None, the provider is unknown, or gemini has no model.
    """
    if settings is None:
        raise ValueError("[create_llm_client] 'settings' is required.")
    api_key = (settings.llm_api_key.get_secret_value() if settings.llm_api_key else None) or None
    if settings.llm_provider == PROVIDER_GEMINI:
        from tracegraph.utilities.llm.gemini_client import GeminiLlmClient

        if not settings.llm_model:
            raise ValueError("[create_llm_client] TG_LLM_MODEL is required when TG_LLM_PROVIDER=gemini "
                             "(e.g. TG_LLM_MODEL=gemini-2.5-pro).")
        client: ILlmClient = GeminiLlmClient(settings.llm_model, settings.llm_max_output_tokens, api_key)
    elif settings.llm_provider == PROVIDER_ANTHROPIC:
        from tracegraph.utilities.llm.anthropic_client import AnthropicLlmClient

        client = AnthropicLlmClient(settings.llm_model or ANTHROPIC_DEFAULT_MODEL, settings.llm_max_output_tokens,
                                    api_key)
    else:
        raise ValueError(f"[create_llm_client] Unknown TG_LLM_PROVIDER {settings.llm_provider!r}. "
                         f"Fix: use {PROVIDER_ANTHROPIC} or {PROVIDER_GEMINI}.")
    logger.info("LLM client created", extra={"provider": settings.llm_provider, "model": settings.llm_model})
    return client
