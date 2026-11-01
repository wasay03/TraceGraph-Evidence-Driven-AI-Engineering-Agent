from abc import ABC, abstractmethod

from tracegraph.schemas.health import HealthResponse


class IHealthService(ABC):
    """
    #Feature: Health
    #Scenario: Contract for service readiness reporting
    #Complexity: Time O(1) - constant
    """

    @abstractmethod
    async def status(self) -> HealthResponse:
        """
        #Feature: Health
        #Scenario: Report application and database readiness
        #Complexity: Time O(1) - constant

        Returns:
            HealthResponse.
        """
