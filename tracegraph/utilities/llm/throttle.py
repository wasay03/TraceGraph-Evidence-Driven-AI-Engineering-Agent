import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

from tracegraph.interfaces.llm import ILlmClient, LlmTurn


class ThrottledLlmClient(ILlmClient):
    """
    #Feature: LLM utility (request pacing)
    #Scenario: Keep at least min_interval seconds between model requests so free-tier per-minute limits are not hit
    #Complexity: Time O(1) per call excluding the wait and the model
    """

    def __init__(self, inner: ILlmClient, min_interval: float,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                 clock: Callable[[], float] = time.monotonic) -> None:
        """
        #Feature: LLM utility (request pacing)
        #Scenario: Wrap a client; sleep and clock are injected for tests
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When inner is None or the interval is negative.
        """
        if inner is None or min_interval < 0:
            raise ValueError("[ThrottledLlmClient.__init__] 'inner' is required and 'min_interval' must be >= 0.")
        self._inner, self._min_interval, self._sleep, self._clock = inner, min_interval, sleep, clock
        self._last: float | None = None
        self._lock = asyncio.Lock()

    async def turn(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LlmTurn:
        """
        #Feature: LLM utility (request pacing)
        #Scenario: Wait out the remaining interval, then forward the turn; concurrent runs share the pace
        #Complexity: Time O(1) excluding the wait and the model
        """
        async with self._lock:
            if self._last is not None:
                remaining = self._min_interval - (self._clock() - self._last)
                if remaining > 0:
                    await self._sleep(remaining)
            self._last = self._clock()
        return await self._inner.turn(system, messages, tools)
