from tracegraph.config import Settings
from tracegraph.containers.repository_container import RepositoryContainer
from tracegraph.interfaces import IWorkspace
from tracegraph.interfaces.services import IHealthService, IOntologyService, IRepoService, ISnapshotService
from tracegraph.ontology import get_registry
from tracegraph.sandbox import GitWorkspace
from tracegraph.services import HealthService, OntologyService, RepoService, SnapshotService


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
        self._workspace: IWorkspace | None = None
        self._health: IHealthService | None = None
        self._ontology: IOntologyService | None = None
        self._repo_service: IRepoService | None = None
        self._snapshots: ISnapshotService | None = None

    @property
    def workspace(self) -> IWorkspace:
        """
        #Feature: Dependency injection
        #Scenario: Lazy git workspace rooted at settings.workspace_dir
        #Complexity: Time O(1) - constant
        """
        if self._workspace is None:
            self._workspace = GitWorkspace(self._settings.workspace_dir)
        return self._workspace

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

    @property
    def ontology(self) -> IOntologyService:
        """
        #Feature: Dependency injection
        #Scenario: Lazy ontology service over the process-wide registry
        #Complexity: Time O(1) - constant
        """
        if self._ontology is None:
            self._ontology = OntologyService(ontology_repository=self._repos.ontology, registry=get_registry())
        return self._ontology

    @property
    def repos(self) -> IRepoService:
        """
        #Feature: Dependency injection
        #Scenario: Lazy repository service
        #Complexity: Time O(1) - constant
        """
        if self._repo_service is None:
            self._repo_service = RepoService(repo_repository=self._repos.repos, workspace=self.workspace)
        return self._repo_service

    @property
    def snapshots(self) -> ISnapshotService:
        """
        #Feature: Dependency injection
        #Scenario: Lazy snapshot service
        #Complexity: Time O(1) - constant
        """
        if self._snapshots is None:
            self._snapshots = SnapshotService(
                snapshot_repository=self._repos.snapshots,
                job_repository=self._repos.jobs,
                repo_repository=self._repos.repos,
                ontology_service=self.ontology,
                workspace=self.workspace,
            )
        return self._snapshots
