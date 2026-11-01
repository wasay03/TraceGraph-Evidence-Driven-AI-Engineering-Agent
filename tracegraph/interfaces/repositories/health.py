from abc import ABC, abstractmethod
from typing import Any


class IHealthRepository(ABC):
    """
    #Feature: Health
    #Scenario: Contract for database readiness checks
    #Complexity: Time O(1) - constant
    """

    @abstractmethod
    async def check(self) -> dict[str, Any]:
        """
        #Feature: Health
        #Scenario: Verify the database answers a stored-function call
        #Complexity: Time O(1) - constant

        Returns:
            Row with status and server_version.
        """
