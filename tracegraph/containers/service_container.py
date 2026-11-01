from tracegraph.config import Settings
from tracegraph.containers.repository_container import RepositoryContainer
from tracegraph.interfaces.services import IHealthService
from tracegraph.services import HealthService


class ServiceContainer:
    """
    #Feature: Dependency injection
    #Scenario: Lazily build services wired to a RepositoryContainer
    #Complexity: Time O(1) - constant per property access
    """

    def __init__(self, repositories: RepositoryContainer, settings: Settings) -> None:
        """
        #Feature: Dependency injection
        #Scenario: Constructor injection of the repository container and settings
        #Complexity: Time O(1) - constant

        Args:
            repositories: RepositoryContainer for this request or job.
            settings: Application settings.

        Raises:
            ValueError: When an argument is None.
        """
        if repositories is None:
            raise ValueError("[ServiceContainer.__init__] 'repositories' is required and must not be None.")
        if settings is None:
            raise ValueError("[ServiceContainer.__init__] 'settings' is required and must not be None.")
        self._repos = repositories
        self._settings = settings
        self._health: IHealthService | None = None

    @property
    def health(self) -> IHealthService:
        """
        #Feature: Dependency injection
        #Scenario: Lazy health service
        #Complexity: Time O(1) - constant
        """
        if self._health is None:
            self._health = HealthService(health_repository=self._repos.health)
        return self._health
