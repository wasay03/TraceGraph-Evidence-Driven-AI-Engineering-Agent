from typing import Any

from tracegraph.interfaces.repositories.health import IHealthRepository
from tracegraph.repositories.base import UdfRepository

_CHECK = "SELECT * FROM tg_health_check()"


class HealthRepository(UdfRepository, IHealthRepository):
    """
    #Feature: Health
    #Scenario: Database readiness via tg_health_check()
    #Complexity: Time O(1) - constant
    """

    async def check(self) -> dict[str, Any]:
        """
        #Feature: Health
        #Scenario: Call tg_health_check and return its single row
        #Complexity: Time O(1) - constant

        Returns:
            Row with status and server_version.

        Raises:
            AppError: When the stored function is missing or the database is unreachable.
        """
        return await self._fetch_one(_CHECK) or {"status": "unknown", "server_version": None}
