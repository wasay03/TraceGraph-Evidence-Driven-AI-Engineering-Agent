import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from tracegraph.constants.llm import RATE_LIMIT_STATUS, RATE_LIMIT_WAIT_SECONDS
from tracegraph.errors import Errors
from tracegraph.interfaces.llm import ILlmClient, LlmTurn

logger = logging.getLogger(__name__)


class FallbackLlmClient(ILlmClient):
    """
    #Feature: LLM utility (API key fallback)
    #Scenario: Same provider and model behind several API keys; a key failure retries the same turn on the next key
               and the working key stays current, so an exhausted key is not retried on every turn
    #Complexity: Time O(k) per turn at worst - one attempt per key, excluding the model
    """

    def __init__(self, clients: list[ILlmClient], rate_limit_wait: float = RATE_LIMIT_WAIT_SECONDS,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        """
        #Feature: LLM utility (API key fallback)
        #Scenario: Clients in priority order, one per key
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When no client is given.
        """
        if not clients:
            raise ValueError("[FallbackLlmClient.__init__] at least one client is required.")
        self._clients, self._current, self._rate_limit_wait, self._sleep = clients, 0, rate_limit_wait, sleep

    async def _try_all(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
                       ) -> tuple[LlmTurn | None, list[Exception]]:
        """
        #Feature: LLM utility (API key fallback)
        #Scenario: One pass over the keys starting at the current one; only key failures move on
        #Complexity: Time O(k) at worst - keys, excluding the model
        """
        count, failures = len(self._clients), []
        for offset in range(count):
            index = (self._current + offset) % count
            try:
                turn = await self._clients[index].turn(system, messages, tools)
            except Errors.LLM.KeyUnavailable as exc:
                failures.append(exc)
                logger.warning("LLM key unavailable", extra={"key_index": index, "reason": exc.message})
                continue
            if index != self._current:
                logger.info("LLM key switched", extra={"from_key_index": self._current, "key_index": index})
                self._current = index
            return turn, failures
        return None, failures

    async def turn(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LlmTurn:
        """
        #Feature: LLM utility (API key fallback)
        #Scenario: Try every key; when all are rate limited, wait out the per-minute window once and try again
        #Complexity: Time O(k) at worst - keys, excluding the wait and the model

        Raises:
            Errors.LLM.KeyUnavailable: When every key failed; names how many were tried and the last failure.
        """
        turn, failures = await self._try_all(system, messages, tools)
        if turn is None and all(f.details.get("status") == RATE_LIMIT_STATUS for f in failures):
            logger.warning("All LLM keys rate limited, waiting", extra={"seconds": self._rate_limit_wait})
            await self._sleep(self._rate_limit_wait)
            turn, failures = await self._try_all(system, messages, tools)
        if turn is not None:
            return turn
        raise Errors.LLM.KeyUnavailable(
            f"All {len(self._clients)} configured LLM API keys are unavailable. Last: {failures[-1].message}",
            {"keys": len(self._clients), "status": failures[-1].details.get("status")}) from failures[-1]
