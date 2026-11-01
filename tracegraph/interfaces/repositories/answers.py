from abc import ABC, abstractmethod
from typing import Any


class IAnswerRepository(ABC):
    """
    #Feature: Reasoning audit
    #Scenario: Contract for persisting engine answers addressable by handle
    #Complexity: Time O(1) per call
    """

    @abstractmethod
    async def insert(self, answer: dict[str, Any], query_ir: dict[str, Any], min_tier: str) -> str:
        """
        #Feature: Reasoning audit
        #Scenario: Store an answer; returns its handle
        #Complexity: Time O(1) - constant
        """

    @abstractmethod
    async def get(self, handle: str) -> dict[str, Any]:
        """
        #Feature: Reasoning audit
        #Scenario: Fetch a stored answer (TG404 when missing)
        #Complexity: Time O(1) - unique index lookup
        """
