from tracegraph.config import Settings
from tracegraph.containers.repository_container import RepositoryContainer
from tracegraph.engine import SnapshotCache
from tracegraph.interfaces import IWorkspace
from tracegraph.interfaces.services import (
    IHealthService,
    IImpactService,
    IIndexingService,
    IOntologyService,
    IQueryService,
    IRepoService,
    ISnapshotService,
)
from tracegraph.ontology import get_registry
from tracegraph.sandbox import GitWorkspace
from tracegraph.services import (
    HealthService,
    ImpactService,
    IndexingService,
    OntologyService,
    QueryService,
    RepoService,
    SnapshotService,
)


class ServiceContainer:
    """
    #Feature: Dependency injection
    #Scenario: Lazily build services wired to a RepositoryContainer
    #Complexity: Time O(1) - constant per property access
    """

    def __init__(self, repositories: RepositoryContainer, settings: Settings,
                 snapshot_cache: SnapshotCache | None = None) -> None:
        """
        #Feature: Dependency injection
        #Scenario: Constructor injection of the repository container and settings
        #Complexity: Time O(1) - constant

        Args:
            repositories: RepositoryContainer for this request or job.
            settings: Application settings.
            snapshot_cache: Process-wide snapshot cache owned by the composition root; a private one if None.

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
        self._indexing: IIndexingService | None = None
        self._query: IQueryService | None = None
        self._impact: IImpactService | None = None
        self._cache = snapshot_cache or SnapshotCache()

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

    @property
    def indexing(self) -> IIndexingService:
        """
        #Feature: Dependency injection
        #Scenario: Lazy indexing service
        #Complexity: Time O(1) - constant
        """
        if self._indexing is None:
            self._indexing = IndexingService(
                graph_repository=self._repos.graph,
                snapshot_repository=self._repos.snapshots,
                job_repository=self._repos.jobs,
                repo_repository=self._repos.repos,
                workspace=self.workspace,
                registry=get_registry(),
            )
        return self._indexing

    @property
    def query(self) -> IQueryService:
        """
        #Feature: Dependency injection
        #Scenario: Lazy query service sharing the process-wide snapshot cache
        #Complexity: Time O(1) - constant
        """
        if self._query is None:
            self._query = QueryService(
                graph_repository=self._repos.graph,
                snapshot_repository=self._repos.snapshots,
                answer_repository=self._repos.answers,
                cache=self._cache,
                registry=get_registry(),
            )
        return self._query

    @property
    def impact(self) -> IImpactService:
        """
        #Feature: Dependency injection
        #Scenario: Lazy impact service built on the query service (shared snapshot cache)
        #Complexity: Time O(1) - constant
        """
        if self._impact is None:
            self._impact = ImpactService(
                query_service=self.query,
                graph_repository=self._repos.graph,
                overlay_repository=self._repos.overlays,
                answer_repository=self._repos.answers,
            )
        return self._impact
