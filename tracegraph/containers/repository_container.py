from sqlalchemy.ext.asyncio import AsyncSession

from tracegraph.interfaces.repositories import IHealthRepository
from tracegraph.repositories import HealthRepository


class RepositoryContainer:
    """
    #Feature: Dependency injection
    #Scenario: Lazily build repositories bound to one database session
    #Complexity: Time O(1) - constant per property access

    One container per request or background job.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        #Feature: Dependency injection
        #Scenario: Bind the container to a session
        #Complexity: Time O(1) - constant

        Args:
            session: Active AsyncSession shared by all repositories in this container.

        Raises:
            ValueError: When session is None.
        """
        if session is None:
            raise ValueError("[RepositoryContainer.__init__] 'session' is required and must not be None.")
        self._session = session
        self._health: IHealthRepository | None = None

    @property
    def health(self) -> IHealthRepository:
        """
        #Feature: Dependency injection
        #Scenario: Lazy health repository
        #Complexity: Time O(1) - constant
        """
        if self._health is None:
            self._health = HealthRepository(self._session)
        return self._health
