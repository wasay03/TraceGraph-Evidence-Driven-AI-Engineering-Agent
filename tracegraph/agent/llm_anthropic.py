import logging
from typing import Any

import anthropic

from tracegraph.constants.agent import AGENT_EFFORT, AGENT_MAX_TOKENS, AGENT_MODEL, FALLBACK_BETA
from tracegraph.errors import Errors
from tracegraph.interfaces.llm import ILlmClient, LlmTurn

logger = logging.getLogger(__name__)


class AnthropicLlmClient(ILlmClient):
    """
    #Feature: Agent LLM boundary
    #Scenario: Claude via the Anthropic SDK: pinned model and effort, adaptive thinking (always on for this model),
               server-side refusal fallback, tool choice auto (forced tool choice is not accepted by this model)
    #Complexity: Time O(1) per call excluding the model
    """

    def __init__(self, client: anthropic.AsyncAnthropic | None = None, model: str = AGENT_MODEL,
                 effort: str = AGENT_EFFORT, max_tokens: int = AGENT_MAX_TOKENS) -> None:
        """
        #Feature: Agent LLM boundary
        #Scenario: Credentials resolve from the environment (ANTHROPIC_API_KEY or an `ant auth login` profile)
        #Complexity: Time O(1) - constant
        """
        self._client = client or anthropic.AsyncAnthropic()
        self._model, self._effort, self._max_tokens = model, effort, max_tokens

    async def _create(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Any:
        """
        #Feature: Agent LLM boundary
        #Scenario: Streamed request (long turns stay clear of HTTP timeouts); the system prompt is cached
        #Complexity: Time O(1) excluding the model
        """
        async with self._client.beta.messages.stream(
            model=self._model,
            max_tokens=self._max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
            tools=tools,
            output_config={"effort": self._effort},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        ) as stream:
            return await stream.get_final_message()

    async def turn(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LlmTurn:
        """
        #Feature: Agent LLM boundary
        #Scenario: One turn; SDK retries 429/5xx/connection errors, remaining failures become typed errors
        #Complexity: Time O(1) excluding the model

        Raises:
            Errors.HTTP.BadRequest: When the request is rejected (4xx other than rate limits).
            Errors.HTTP.InternalServerError: When the API stays unavailable after retries.
        """
        try:
            response = await self._create(system, messages, tools)
        except anthropic.BadRequestError as exc:
            raise Errors.HTTP.BadRequest(f"LLM request rejected: {exc.message}") from exc
        except anthropic.RateLimitError as exc:
            raise Errors.HTTP.InternalServerError("LLM rate limit persisted after retries.") from exc
        except anthropic.APIStatusError as exc:
            raise Errors.HTTP.InternalServerError(f"LLM API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise Errors.HTTP.InternalServerError("LLM API unreachable.") from exc
        content = [block.model_dump(mode="json", exclude_none=True) for block in response.content]
        refusal = None
        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            refusal = getattr(details, "category", None) or "refusal"
        logger.info("LLM turn", extra={"model": response.model, "stop_reason": response.stop_reason,
                                       "output_tokens": response.usage.output_tokens})
        return LlmTurn(content, response.stop_reason, response.usage.input_tokens, response.usage.output_tokens,
                       response.model, refusal, [b for b in content if b.get("type") == "tool_use"])
