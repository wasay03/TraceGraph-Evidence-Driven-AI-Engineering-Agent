import logging

from tracegraph.errors import AppError
from tracegraph.interfaces.repositories.health import IHealthRepository
from tracegraph.interfaces.services.health import IHealthService
from tracegraph.schemas.health import HealthResponse

logger = logging.getLogger(__name__)


class HealthService(IHealthService):
    """
    #Feature: Health
    #Scenario: Combine process liveness with database readiness
    #Complexity: Time O(1) - constant
    """

    def __init__(self, health_repository: IHealthRepository) -> None:
        """
        #Feature: Health
        #Scenario: Constructor injection of the health repository
        #Complexity: Time O(1) - constant

        Args:
            health_repository: Repository implementing IHealthRepository.

        Raises:
            ValueError: When health_repository is None.
        """
        if health_repository is None:
            raise ValueError("[HealthService.__init__] 'health_repository' is required and must not be None.")
        self._repo = health_repository

    async def status(self) -> HealthResponse:
        """
        #Feature: Health
        #Scenario: Report ok when the database answers, degraded otherwise
        #Complexity: Time O(1) - constant

        Returns:
            HealthResponse; never raises for a database outage.
        """
        try:
            row = await self._repo.check()
            return HealthResponse(status="ok", database=row["status"], server_version=row["server_version"])
        except AppError as exc:
            logger.warning("Database health check failed", extra={"code": exc.code})
            return HealthResponse(status="degraded", database="unavailable")
