import logging
from typing import Any

import anthropic

from tracegraph.constants.llm import ANTHROPIC_EFFORT, ANTHROPIC_FALLBACK_BETA, STOP_REFUSAL
from tracegraph.errors import Errors
from tracegraph.interfaces.llm import ILlmClient, LlmTurn

logger = logging.getLogger(__name__)


class AnthropicLlmClient(ILlmClient):
    """
    #Feature: LLM utility (Anthropic adapter)
    #Scenario: Claude via the Anthropic SDK: pinned model and effort, adaptive thinking, server-side refusal fallback,
               tool choice auto. The neutral message format is the Messages API shape, so no translation is needed.
    #Complexity: Time O(1) per call excluding the model
    """

    def __init__(self, model: str, max_tokens: int, api_key: str | None = None,
                 client: anthropic.AsyncAnthropic | None = None) -> None:
        """
        #Feature: LLM utility (Anthropic adapter)
        #Scenario: Without api_key the SDK resolves ANTHROPIC_API_KEY or an `ant auth login` profile
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When model is empty.
        """
        if not model:
            raise ValueError("[AnthropicLlmClient.__init__] 'model' is required.")
        if client is None:
            client = anthropic.AsyncAnthropic(api_key=api_key) if api_key else anthropic.AsyncAnthropic()
        self._client, self._model, self._max_tokens = client, model, max_tokens

    async def _create(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Any:
        """
        #Feature: LLM utility (Anthropic adapter)
        #Scenario: Streamed request (long turns stay clear of HTTP timeouts); the system prompt is cached
        #Complexity: Time O(1) excluding the model
        """
        async with self._client.beta.messages.stream(
            model=self._model,
            max_tokens=self._max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
            tools=tools,
            output_config={"effort": ANTHROPIC_EFFORT},
            betas=[ANTHROPIC_FALLBACK_BETA],
            fallbacks="default",
        ) as stream:
            return await stream.get_final_message()

    async def turn(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LlmTurn:
        """
        #Feature: LLM utility (Anthropic adapter)
        #Scenario: One turn; the SDK retries 429/5xx/connection errors, remaining failures become typed errors
        #Complexity: Time O(1) excluding the model

        Raises:
            Errors.LLM.KeyUnavailable: When the key is invalid, forbidden or out of quota after retries.
            Errors.HTTP.BadRequest: When the request is rejected.
            Errors.HTTP.InternalServerError: When the API stays unavailable after retries.
        """
        try:
            response = await self._create(system, messages, tools)
        except anthropic.BadRequestError as exc:
            raise Errors.HTTP.BadRequest(f"LLM request rejected: {exc.message}") from exc
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError, anthropic.RateLimitError) as exc:
            raise Errors.LLM.KeyUnavailable(f"Anthropic key failed ({exc.status_code}).",
                                            {"status": exc.status_code}) from exc
        except anthropic.APIStatusError as exc:
            raise Errors.HTTP.InternalServerError(f"LLM API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise Errors.HTTP.InternalServerError("LLM API unreachable.") from exc
        content = [block.model_dump(mode="json", exclude_none=True) for block in response.content]
        refusal = None
        if response.stop_reason == STOP_REFUSAL:
            refusal = getattr(getattr(response, "stop_details", None), "category", None) or STOP_REFUSAL
        logger.info("LLM turn", extra={"provider": "anthropic", "model": response.model,
                                       "stop_reason": response.stop_reason, "output_tokens": response.usage.output_tokens})
        return LlmTurn(content, response.stop_reason, response.usage.input_tokens, response.usage.output_tokens,
                       response.model, refusal, [b for b in content if b.get("type") == "tool_use"])
