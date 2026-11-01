import logging
from typing import Any

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

    def __init__(self, clients: list[ILlmClient]) -> None:
        """
        #Feature: LLM utility (API key fallback)
        #Scenario: Clients in priority order, one per key
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When no client is given.
        """
        if not clients:
            raise ValueError("[FallbackLlmClient.__init__] at least one client is required.")
        self._clients, self._current = clients, 0

    async def turn(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LlmTurn:
        """
        #Feature: LLM utility (API key fallback)
        #Scenario: Try the current key, then the others in order; only key failures move on, other errors surface
        #Complexity: Time O(k) at worst - keys, excluding the model

        Raises:
            Errors.LLM.KeyUnavailable: When every key failed; names how many were tried and the last failure.
        """
        count, last = len(self._clients), None
        for offset in range(count):
            index = (self._current + offset) % count
            try:
                turn = await self._clients[index].turn(system, messages, tools)
            except Errors.LLM.KeyUnavailable as exc:
                last = exc
                logger.warning("LLM key unavailable", extra={"key_index": index, "reason": exc.message})
                continue
            if index != self._current:
                logger.info("LLM key switched", extra={"from_key_index": self._current, "key_index": index})
                self._current = index
            return turn
        raise Errors.LLM.KeyUnavailable(f"All {count} configured LLM API keys are unavailable. Last: {last.message}",
                                        {"keys": count}) from last
